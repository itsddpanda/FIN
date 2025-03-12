# File: routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging
import os
from db import get_db
from models import User, Folio
from schemas import UserOut
from auth import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/users", tags=["Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

logger_module = logging.getLogger(__name__)

def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    # If middleware already set the user email, use it.
    if hasattr(request.state, "user_email") and request.state.user_email != "Anonymous":
        email = request.state.user_email
        logger_module.info("Got email from request")
    else:
        # Fallback: decode the token if for some reason the middleware didn't set it.
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
            logger_module.info("Got email from JWT")
            if email is None:
                logger_module.info("No email found in token payload.")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except JWTError:
            logger_module.info("JWT error during token decoding.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    # Now, query the database using the email (as sub contains the email)
    # Fetch all folio records for the user with the given email.
    user = db.query(User).filter(User.email == email).first()
    folios = db.query(Folio).join(User, Folio.user_id == User.user_id).filter(User.email == email).all()
    if not folios:
        logger_module.info("User folio record not found; redirecting to /users/getstarted")
        # Return a RedirectResponse if the user is new (i.e. no record in DB)
        return JSONResponse(
                content={"detail": "Unauthorized. Please log in", "status" : "Error"},
                status_code=401
            )
    return user

# Endpoint to fetch current user details (if user exists)
@router.get("/me", response_model=UserOut)
def read_users_me(current_user = Depends(get_current_user)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    logger_module.info("User validated via /me endpoint.")
    return current_user

# Dashboard route: user must have a record; otherwise, redirect.
@router.get("/dashboard")
def dashboard(current_user = Depends(get_current_user)):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return {
        "message": f"Welcome to your dashboard, {current_user.full_name or current_user.email}!"
    }

# Updated file upload endpoint using FastAPI's UploadFile and Form dependencies.
@router.post("/getstarted")
async def upload_file(
    file: UploadFile = File(...),
    password: str = Form(...)
):
    # Define the upload folder and ensure it exists.
    UPLOAD_FOLDER = os.path.join("pwd", "upload")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    file_location = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_location, "wb") as f:
        content = await file.read()
        f.write(content)
    # (Optionally) Process the 'password' for file encryption or validation.
    logger_module.info(f"Received file '{file.filename}' with provided password.")

    return {"detail": f"File uploaded successfully to {file_location}"}