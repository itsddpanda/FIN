# File: db.py
from sqlalchemy import create_engine, exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.exc import OperationalError
from alembic import command
from alembic.config import Config
from alembic.util import CommandError
from logging_config import logger, DBURL
import psycopg2
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

def check_and_create_db():
    if DBURL.startswith("postgresql"):
        try:
            url_parts = DBURL.split("//")[1].split("@")[0].split(":")
            user = url_parts[0]
            password = url_parts[1]
            host_port = DBURL.split("@")[1].split("/")[0].split(":")
            host = host_port[0]
            port = host_port[1] if len(host_port) > 1 else "5432"
            db_name = DBURL.split("/")[-1]

            conn = psycopg2.connect(user=user, password=password, host=host, port=port, database="postgres")
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname='{db_name}'")
            exists = cur.fetchone()
            if not exists:
                cur.execute(f"CREATE DATABASE {db_name}")
                logger.info(f"Database '{db_name}' created.")
            cur.close()
            conn.close()
        except psycopg2.OperationalError as e:
            logger.error(f"Error checking/creating database: {e}")
            raise

def run_migrations():
    try:
        logger.info("Running Alembic migrations...")
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except CommandError as alembic_err:
        logger.error(f"Alembic migration command error: {alembic_err}")
        # Consider implementing rollback or manual intervention here
        raise
    except OperationalError as db_err:
        logger.error(f"Database error during migrations: {db_err}")
        # Consider implementing retry logic or database connection checks here
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during migrations: {e}")
        # Consider implementing rollback or manual intervention here
        raise

def init_db():
    check_and_create_db()
    run_migrations()