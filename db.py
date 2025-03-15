# File: db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from logging_config import logger, DBURL
import logging


logger = logging.getLogger("db.py")
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

def init_db():
    logger.info("INIT DB")
    Base.metadata.create_all(bind=engine)
    logger.info("DB INITIALIZED")