import logging
import sys
from typing import Any


def setup_logging():
    """Configure structured logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


class StructuredLogger:
    """Logger with structured logging support."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def info(self, message: str, **kwargs: Any):
        """Log info with structured data."""
        extra_data = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.info(f"{message} {extra_data}" if extra_data else message)

    def error(self, message: str, **kwargs: Any):
        """Log error with structured data."""
        extra_data = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.error(f"{message} {extra_data}" if extra_data else message)

    def warning(self, message: str, **kwargs: Any):
        """Log warning with structured data."""
        extra_data = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.warning(f"{message} {extra_data}" if extra_data else message)

    def debug(self, message: str, **kwargs: Any):
        """Log debug with structured data."""
        extra_data = " ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.logger.debug(f"{message} {extra_data}" if extra_data else message)
