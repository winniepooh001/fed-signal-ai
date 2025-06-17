import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class ScreenerLogger:
    """Centralized logging configuration for the screener system"""

    _initialized = False
    _logger = None

    @classmethod
    def initialize(cls,
                   log_level: str = "INFO",
                   log_file: Optional[str] = None,
                   log_dir: str = "logs",
                   max_file_size: int = 10 * 1024 * 1024,  # 10MB
                   backup_count: int = 5,
                   console_output: bool = True) -> logging.Logger:
        """
        Initialize the centralized logging system

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Custom log file name (default: unified_YYYYMMDD.log)
            log_dir: Directory for log files
            max_file_size: Maximum size of each log file before rotation
            backup_count: Number of backup files to keep
            console_output: Whether to output logs to console

        Returns:
            Main logger instance
        """

        if cls._initialized:
            return cls._logger

        # Create logs directory if it doesn't exist
        Path(log_dir).mkdir(exist_ok=True)

        # Set default log file name with timestamp
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = f"unified_{timestamp}.log"

        log_path = os.path.join(log_dir, log_file)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))

        # Clear any existing handlers
        root_logger.handlers.clear()

        # Create formatters with line numbers prominently displayed
        detailed_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)-4d | %(funcName)s() | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        console_formatter = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)-4d | %(message)s',
            datefmt='%H:%M:%S'
        )

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # File gets all messages
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)

        # Console handler
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, log_level.upper()))
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # Create unified application logger
        cls._logger = logging.getLogger('unified_screener')
        cls._logger.setLevel(logging.DEBUG)

        # Log system initialization
        cls._logger.info("=" * 60)
        cls._logger.info("UNIFIED SCREENER SYSTEM STARTING")
        cls._logger.info(f"Log Level: {log_level.upper()}")
        cls._logger.info(f"Log File: {log_path}")
        cls._logger.info(f"Console Output: {console_output}")
        cls._logger.info("All modules will log to this unified logger")
        cls._logger.info("=" * 60)

        cls._initialized = True
        return cls._logger

    @classmethod
    def get_logger(cls, name: str = None) -> logging.Logger:
        """
        Get the unified logger instance (ignores name parameter for unified logging)

        Args:
            name: Module name (ignored - kept for backwards compatibility)

        Returns:
            Unified logger instance
        """

        if not cls._initialized:
            raise RuntimeError("Logger not initialized. Call ScreenerLogger.initialize() first.")

        # Always return the unified logger regardless of name parameter
        return cls._logger

    @classmethod
    def set_level(cls, level: str):
        """Change the logging level dynamically"""
        if cls._initialized:
            logging.getLogger().setLevel(getattr(logging, level.upper()))
            cls._logger.info(f"Log level changed to {level.upper()}")

    @classmethod
    def log_system_info(cls):
        """Log system and environment information"""
        if not cls._initialized:
            return

        import platform
        import psutil

        logger = cls._logger
        logger.info("SYSTEM INFORMATION:")
        logger.info(f"  Python Version: {platform.python_version()}")
        logger.info(f"  Platform: {platform.platform()}")
        logger.info(f"  CPU Count: {psutil.cpu_count()}")
        logger.info(f"  Memory: {psutil.virtual_memory().total / (1024 ** 3):.1f} GB")
        logger.info(f"  Disk Space: {psutil.disk_usage('/').total / (1024 ** 3):.1f} GB")


# Convenience functions for easy access
def get_logger(name="Screener") -> logging.Logger:
    if not ScreenerLogger._initialized:
        ScreenerLogger.initialize()  # Default to INFO with no file
    return ScreenerLogger._logger.getChild(name)


def initialize_logging(log_level: str = "INFO", **kwargs) -> logging.Logger:
    """Initialize logging - convenience function"""
    return ScreenerLogger.initialize(log_level=log_level, **kwargs)


# Context manager for temporary log level changes
class LogLevel:
    """Context manager for temporarily changing log level"""

    def __init__(self, level: str):
        self.new_level = level.upper()
        self.old_level = None

    def __enter__(self):
        self.old_level = logging.getLogger().level
        ScreenerLogger.set_level(self.new_level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.old_level:
            logging.getLogger().setLevel(self.old_level)