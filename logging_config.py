import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)

logger = logging.getLogger("fastapi")
logger.setLevel(getattr(logging, log_level, logging.INFO))

# Print log level (for debugging)
print(f"Logging initialized. Log level set to: {logging.getLevelName(logger.level)}")
