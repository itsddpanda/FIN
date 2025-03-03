# File: schemas.py
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    is_active: bool
    user_id: str

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
