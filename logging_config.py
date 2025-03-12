# file: logging_config.py
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
DBURL = os.getenv("DATABASE_URL")
# Configure root logger
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),  # Set root logger level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)

# Ensure the root logger respects the log level
logger = logging.getLogger()  # Get the root logger
logger.setLevel(getattr(logging, log_level, logging.INFO))  # Explicitly set level

print(f"Logging initialized. Log level set to: {logging.getLevelName(logger.level)}")
