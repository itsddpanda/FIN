# File: routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging

from db import get_db
from models import User
from schemas import UserOut
from auth import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/users", tags=["Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logger_module = logging.getLogger(__name__)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            logger_module.info("Empty email")
            raise credentials_exception
    except JWTError:
        logger_module.info("JWTerror")
        raise credentials_exception
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        logger_module.info("Empty User")
        raise credentials_exception
    logger_module.info(f"USER Validation Complete {user}")
    return user

@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    logger_module.info("User valid")
    return current_user
