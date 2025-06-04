"""Utility helpers for AlphaPulse."""

import logging

# Initialize a module level logger. Configuration is applied in ``config.py``.
logger = logging.getLogger("AlphaPulse")


def log(msg, level=logging.INFO):
    """Log ``msg`` with the specified log ``level`` (default INFO)."""

    logger.log(level, msg)
