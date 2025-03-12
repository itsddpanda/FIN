# File: routes/auth.py
from venv import logger
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from db import get_db
from models import User
from schemas import Token, UserOut, UserCreate
from auth import verify_password, get_password_hash, create_access_token, generate_userid

router = APIRouter(prefix="/auth", tags=["Authentication"]) 

@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    try:
    # Check if user already exists
        logger.info(f"{user.email} {user.password}")
        db_user = db.query(User).filter(User.email == user.email).first()
    except Exception as e:
        logger.error(f"Unable to read DB {e}")
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail="Unable to read DB or something like that")

    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    hashed_password = get_password_hash(user.password)
    user_id = generate_userid()
    new_user = User(email=user.email, hashed_password=hashed_password, user_id= user_id)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}
