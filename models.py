# File: models.py
from sqlalchemy import Column, String, Boolean
from db import Base

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    full_name = Column(String)
