import logging
import sys
from datetime import datetime
from typing import Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name"""
    return logging.getLogger(name)

def log_api_error(logger: logging.Logger, error: Exception, context: Dict[str, Any] = None) -> None:
    """Log API errors with context"""
    error_details = {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'timestamp': datetime.utcnow().isoformat(),
        'context': context or {}
    }
    logger.error(f"API Error: {error_details}")

def log_s3_operation(logger: logging.Logger, operation: str, details: Dict[str, Any]) -> None:
    """Log S3 operations with details"""
    log_entry = {
        'operation': operation,
        'timestamp': datetime.utcnow().isoformat(),
        **details
    }
    logger.info(f"S3 Operation: {log_entry}")
