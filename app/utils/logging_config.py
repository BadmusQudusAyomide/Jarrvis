import logging
import logging.handlers
import os
from datetime import datetime

# Create logs directory
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Log file paths
APP_LOG_FILE = os.path.join(LOGS_DIR, "jarvis.log")
ERROR_LOG_FILE = os.path.join(LOGS_DIR, "error.log")
AGENT_LOG_FILE = os.path.join(LOGS_DIR, "agent.log")

# Log format
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    """Set up structured logging for the entire application."""
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler - INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Main application log file - INFO and above, rotates at 10MB
    file_handler = logging.handlers.RotatingFileHandler(
        APP_LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Error log file - ERROR and above
    error_handler = logging.handlers.RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
        DATE_FORMAT
    )
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)
    
    # Agent-specific logger
    agent_logger = logging.getLogger("app.agents")
    agent_handler = logging.handlers.RotatingFileHandler(
        AGENT_LOG_FILE,
        maxBytes=10*1024*1024,
        backupCount=3,
        encoding='utf-8'
    )
    agent_handler.setLevel(logging.DEBUG)
    agent_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s | %(message)s",
        DATE_FORMAT
    )
    agent_handler.setFormatter(agent_formatter)
    agent_logger.addHandler(agent_handler)
    
    # Log startup
    root_logger.info("="*60)
    root_logger.info("Jarvis AI Logging Started")
    root_logger.info(f"Log files: {LOGS_DIR}")
    root_logger.info("="*60)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)
