"""
Structured Logging Module for IRCTC-Style Train Reservation Server
Ensures clean, thread-safe logging with automated sanitization of sensitive credentials.
"""

import logging
import os
import re
from typing import Optional

# Sensitive patterns to redact from logs
SENSITIVE_PATTERNS = [
    (re.compile(r'("password"\s*:\s*")([^"]+)(")', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'("token"\s*:\s*")([^"]+)(")', re.IGNORECASE), r'\1***REDACTED***\3'),
    (re.compile(r'(password=)([^&\s]+)', re.IGNORECASE), r'\1***REDACTED***'),
    (re.compile(r'(secret=)([^&\s]+)', re.IGNORECASE), r'\1***REDACTED***'),
]


class CredentialSanitizingFilter(logging.Filter):
    """
    Log filter that intercepts and sanitizes passwords, auth tokens,
    and database credentials before records are written.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            sanitized = record.msg
            for pattern, repl in SENSITIVE_PATTERNS:
                sanitized = pattern.sub(repl, sanitized)
            record.msg = sanitized

        if record.args:
            if isinstance(record.args, dict):
                clean_args = {}
                for k, v in record.args.items():
                    if any(secret in k.lower() for secret in ["password", "token", "secret", "hash"]):
                        clean_args[k] = "***REDACTED***"
                    else:
                        clean_args[k] = v
                record.args = clean_args
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    "***REDACTED***" if isinstance(a, str) and any(s in a.lower() for s in ["pass", "token"]) else a
                    for a in record.args
                )
        return True


def setup_logger(
    name: str = "IRCTC-Server",
    log_level: Optional[str] = None,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Configures and returns a thread-safe, sanitized logger instance.
    """
    level_name = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [Thread-%(thread)d] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    sanitizer = CredentialSanitizingFilter()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sanitizer)
    logger.addHandler(console_handler)

    # Optional File Handler
    target_file = log_file or os.getenv("LOG_FILE", "logs/server.log")
    try:
        log_dir = os.path.dirname(target_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(target_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sanitizer)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning("Could not initialize file logging at %s: %s", target_file, str(e))

    return logger


# Default server logger
logger = setup_logger()
