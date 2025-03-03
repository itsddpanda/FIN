# File: db.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import sys
import logging
from dotenv import load_dotenv
load_dotenv()

# Get Log level for .env
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
# Configure logging
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),  
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),  
        logging.FileHandler("app.log")  
    ]
)
logger = logging.getLogger("fastapi")
logger.setLevel(getattr(logging, log_level, logging.INFO))

# Use environment variables to configure your database URL securely
DATABASE_URL = os.getenv("DATABASE_URL")
logger.info(f"DB URL fetched from .env file")
logger.debug(f"from DB.PY Database : {DATABASE_URL}")

# For SQLite, include connect_args; otherwise, remove or adjust accordingly
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session in routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
