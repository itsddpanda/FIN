#File: alembic/env.py
import os
from logging.config import fileConfig
from sqlalchemy import create_engine
import logging
from alembic import context
from models import User, StatementPeriod, Folio, Scheme, Valuation, Transaction
from db import Base  # Import your Base from db.py
from dotenv import load_dotenv
import sys
load_dotenv()
# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata  # Corrected to point to Base.metadata
# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = os.getenv("DATABASE_URL")  # Get DATABASE_URL from environment
    logger.debug(f"From ENV.PY Offline Migration: {url}")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(os.getenv("DATABASE_URL"))  # Create engine directly
    logger.debug(f"From env.py online migration Connectable : {connectable}")
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()