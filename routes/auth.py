# File: routes/auth.py
from logging_config import logger
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from db import get_db
from models import User
from schemas import Token, UserOut, UserCreate, Usernoid
from auth import verify_password, get_password_hash, create_access_token, generate_userid

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logger.getChild("auth.py")

@router.post("/register", response_model=Usernoid)
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
        logger.info(f"Registering user with email: {user.email}")
        db_user = db.query(User).filter(User.email == user.email).first()

        if db_user:
            if db_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered and active",
                )
            else:
                hashed_password = get_password_hash(user.password)
                db_user.hashed_password = hashed_password
                db_user.is_active = True
                db.commit()
                db.refresh(db_user)
                logger.info(f"User {user.email} re-registered")
                return Usernoid.model_validate(db_user)

        hashed_password = get_password_hash(user.password)
        user_id = generate_userid()
        new_user = User(email=user.email, hashed_password=hashed_password, user_id=user_id, is_active=True) # very important to set is_active to true
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info(f"New user registered with ID: {user_id}")
        return Usernoid.model_validate(new_user)

    except HTTPException as http_exc:
        raise http_exc # re-raise the http exception
    except Exception as e:
        logger.error(f"Error during registration: {e}", exc_info=True)
        db.rollback() # important to rollback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration",
        )


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == form_data.username).first()
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")
        elif user and not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
        access_token = create_access_token(data={"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Unable to login.. {e}", exc_info=False)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login",
        )
