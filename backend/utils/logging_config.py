import logging
import json
import sys
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter that captures all extra fields dynamically."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Standard log fields
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Capture "extra" fields dynamically
        # We skip standard LogRecord attributes to only get user-provided data
        standard_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
            'funcName', 'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'msg', 'name', 'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'thread', 'threadName'
        }
        
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                log_entry[key] = value
        
        # Add exception info if it exists
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

class StructuredLogger:
    """Structured JSON logger with Rotating File support."""
    
    def __init__(self, name: str, log_file: str = 'app.log'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Avoid duplicate logs in some frameworks
        
        # Clear existing handlers to prevent duplicates on reload
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        
        formatter = JSONFormatter()

        # 1. CONSOLE HANDLER (Standard Output)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 2. ROTATING FILE HANDLER
        # maxBytes=10MB, keeping 5 backup files
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=10 * 1024 * 1024, 
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        # Typically, we log everything INFO and above to the file in prod
        file_handler.setLevel(logging.INFO) 
        self.logger.addHandler(file_handler)
    
    def info(self, message: str, **kwargs):
        self.logger.info(message, extra=kwargs)
    
    def error(self, message: str, exc_info=True, **kwargs):
        # exc_info=True automatically captures the stack trace if in an 'except' block
        self.logger.error(message, exc_info=exc_info, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        self.logger.warning(message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        self.logger.debug(message, extra=kwargs)

# Singleton management
_loggers = {}

def get_logger(name: str = "app_logger") -> StructuredLogger:
    """Get or create a structured logger singleton."""
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]