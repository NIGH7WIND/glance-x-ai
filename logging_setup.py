import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging() -> None:
    """
    Central logging setup.

    Env vars:
      - OVERLAY_LOG_LEVEL: DEBUG|INFO|WARNING|ERROR (default: INFO)
      - OVERLAY_LOG_FILE: if set, also logs to this file (rotating)
      - OVERLAY_LOG_FILE_MAX_BYTES: default 10485760 (10MB)
      - OVERLAY_LOG_FILE_BACKUP_COUNT: default 5
    """
    log_level_str = os.getenv("OVERLAY_LOG_LEVEL", "INFO").upper().strip()
    level = getattr(logging, log_level_str, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on hot-reload / repeated setup.
    if getattr(root, "_overlay_logging_configured", False):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    log_file = os.getenv("OVERLAY_LOG_FILE")
    if log_file:
        try:
            max_bytes = int(os.getenv("OVERLAY_LOG_FILE_MAX_BYTES", "10485760"))
            backup_count = int(os.getenv("OVERLAY_LOG_FILE_BACKUP_COUNT", "5"))
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except Exception:
            # Don’t fail the app if file logging misconfigures.
            root.exception("Failed to set up file logging; continuing with console only.")

    root._overlay_logging_configured = True
