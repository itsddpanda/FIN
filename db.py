# File: db.py
from sqlalchemy import create_engine, exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from logging_config import logger, DBURL
import time

# Use environment variables to configure your database URL securely
DATABASE_URL = DBURL
if not DBURL:
    logger.error("DATABASE_URL environment variable is not set.")
    raise ValueError("DATABASE_URL environment variable is not set.")

logger.info(f"DB URL fetched from .env file")
logger.debug(f"from DB.PY Database : {DATABASE_URL}")

# For SQLite, include connect_args; otherwise, remove or adjust accordingly
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
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

def create_tables(max_retries=5, retry_delay=5):
    retries = 0
    while retries < max_retries:
        try:
            logger.info("Attempting to create tables...")
            Base.metadata.create_all(bind=engine)
            logger.info("Tables created successfully.")
            return  # Success, exit the function
        except exc.OperationalError as e:
            logger.error(f"Database error during table creation: {e}. Retry {retries + 1}/{max_retries}")
            retries += 1
            time.sleep(retry_delay)
    logger.error("Failed to create tables after multiple retries.")
    raise RuntimeError("Failed to create tables.")