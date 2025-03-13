# File: db.py
from sqlalchemy import create_engine, text 
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.environment import MigrationContext
from logging_config import logger, DBURL
import logging
import psycopg2
import os
from datetime import datetime

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

def check_and_create_db(engine):
    """Checks if any tables exist in the database."""
    logger.info("Initializing table existence check...")
    try:
        with engine.connect() as connection:
            logger.info("Fetching table information...")
            result = connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public');")
            ).fetchone()
            exists = result[0]
            if exists:
                logger.info("Tables found in the database. Was it initialized with Alembic? Checking...")
                result = connection.execute(text("SELECT version_num FROM alembic_version;")).fetchone()
                logger.info(f"Found Version {result[0]}, should be ok to run migration.")
                return True
            else:
                logger.info("No tables found in the database.")
                return False

    except psycopg2.OperationalError as e:
        logger.error(f"Error checking for tables: {e}")
        return True # Return True to still run migrations.
    except Exception as e:
        logger.error(f"Error checking for tables: {e}")
        return True # Return True to still run migrations.

def get_current_revision():
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()
    
def run_migrations():
    try:
        logger.info("Initializing Alembic Migration configuration...")
        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)

        # If no migration scripts exist, auto-generate one
        if not list(script.walk_revisions()):
            logger.info("No migration scripts found. Creating initial migration...")

            # Generate a new migration
            migration_message = f"Auto migration {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            os.system(f"alembic revision --autogenerate -m \"{migration_message}\"")
        
        # Run migrations if needed
        current_rev = get_current_revision()
        heads = script.get_heads()
        if current_rev in heads:
            logger.info("Database is already up-to-date. No migrations to run.")
            return
        
        logger.info("Starting upgrade to head...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations completed successfully.")
    except Exception as e:
        logger.exception(f"Unexpected error during migrations: {e}")

def init_db():
    logger.info("INIT DB")
    try:
        if not os.path.exists("alembic.ini") or not os.path.exists("alembic"):
            logger.info("Alembic is not initialized. Initializing. Paused on Init for further check..")
            os.system("alembic init alembic")
        else:
            logger.info("Alembic Directory exisits. Skipping Init")
        
        # Ensure tables exist
        if check_and_create_db(engine):
            logger.info("Check AND CREATE is true...Alembic is initialized. Run Migration...")
            run_migrations()
        else:
            logger.info("Check 2...Alembic is initialized. But no table found...")
            run_migrations()
    except Exception as e:
        logger.exception(f"Error initializing database: {e}", exc_info=False)