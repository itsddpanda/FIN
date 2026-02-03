from csv import excel_tab
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from logging_config import logger  # Ensure this is correctly initialized before import
import redis

#connect to redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

logger = logging.getLogger("env")

# Load DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.error("DATABASE_URL is not set.")
    raise ValueError("DATABASE_URL is not set.")

# ✅ Convert for Async if using PostgreSQL
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://") if DATABASE_URL.startswith("postgresql://") else DATABASE_URL

# logger.debug(f"Sync Database URL: {DATABASE_URL}")
# logger.debug(f"Async Database URL: {ASYNC_DATABASE_URL}")

# ✅ Sync Engine (For APIs)
sync_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,           # Set pool size (adjust based on load)
    max_overflow=20         # Allow additional connections beyond the pool
)

# ✅ Async Engine (For Background Tasks)
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,             # Set to False in production
    pool_pre_ping=True
)

# ✅ Sync Session Factory (For APIs)
SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False
)

# ✅ Async Session Factory (For Background Tasks)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# ✅ Base Model
Base = declarative_base()

# ✅ Sync DB Dependency (For APIs)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ✅ Async DB Dependency (For Background Tasks)
async def get_async_db():
    async with AsyncSessionLocal() as db:
        yield db

# ✅ Sync Database Initialization (Only for Local Development)
def init_db():
    logger.info("Initializing Database...")
    try:
        Base.metadata.create_all(bind=sync_engine)
        logger.info("✅ Database Initialized") 
        # logger.info(Base.metadata.drop_all(bind=sync_engine))
    except Exception as e:
        logger.error(f"❌ Failed to connect to Postgres DB")

# ✅ Async Database Initialization (For Background Tasks & Development)
async def async_init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Async Database Initialized")

def init_redis():
    try:
        redis_client.ping()  # Check if Redis is reachable
        logger.info("✅ Redis is connected")
    except redis.ConnectionError:
        logger.warning("❌ Redis connection failed")
