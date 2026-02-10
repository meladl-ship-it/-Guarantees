
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

class Logger:
    _instance = None

    @staticmethod
    def get_instance():
        if Logger._instance is None:
            Logger._instance = Logger._setup_logger()
        return Logger._instance

    @staticmethod
    def _setup_logger():
        logger = logging.getLogger("GuaranteesApp")
        logger.setLevel(logging.DEBUG)

        # Create logs directory if it doesn't exist
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "app.log")

        # File Handler (Rotating)
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

def log_info(msg):
    Logger.get_instance().info(msg)

def log_error(msg, exc_info=True):
    Logger.get_instance().error(msg, exc_info=exc_info)

def log_debug(msg):
    Logger.get_instance().debug(msg)

def log_warning(msg):
    Logger.get_instance().warning(msg)
