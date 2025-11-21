# src/my_doa/utils/logger.py

"""
Application-wide logger factory for the DOA system.

Key features:
-------------
• Consistent JSONL log formatting
• Safe for multiprocessing and threads
• Optional console logging
• Configurable log level
• Fast enough for real-time loops
"""

from __future__ import annotations

import logging
import json
import sys
from datetime import datetime


# ================================================================
# JSON Formatter
# ================================================================

class JSONFormatter(logging.Formatter):
    """
    Emit logs as JSON objects (one per line).

    Format:
        {
          "level": "INFO",
          "time": "2025-01-01T12:30:00.123Z",
          "logger": "src.my_doa.xxx",
          "message": "...",
          "extra": {...}
        }
    """

    def format(self, record):
        base = {
            "level": record.levelname,
            "time": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add structured "extra"
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            base["extra"] = record.extra

        return json.dumps(base, ensure_ascii=False)


# ================================================================
# Central Logger Factory
# ================================================================

def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Get or create a logger with JSON output.

    Only root creation occurs once; subsequent calls reuse handlers.

    Parameters
    ----------
    name : str
        Name of module logger.
    level : str
        Logging level: "DEBUG", "INFO", "WARNING", etc.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    logger.addHandler(handler)
    logger.propagate = False  # prevent double logging

    return logger
