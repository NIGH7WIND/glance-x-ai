import logging
import logging.config
import os


def setup_logging() -> None:
    """
    Central logging setup via dictConfig.

    Env vars:
      - OVERLAY_LOG_LEVEL: DEBUG|INFO|WARNING|ERROR (default: INFO)
      - OVERLAY_LOG_FILE: if set, also logs to this file (rotating)
      - OVERLAY_LOG_FILE_MAX_BYTES: default 10485760 (10MB)
      - OVERLAY_LOG_FILE_BACKUP_COUNT: default 5
    """
    level = os.getenv("OVERLAY_LOG_LEVEL", "INFO").upper().strip()

    handlers: dict = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": level,
        }
    }

    log_file = os.getenv("OVERLAY_LOG_FILE")
    if log_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "level": level,
            "filename": log_file,
            "maxBytes": int(os.getenv("OVERLAY_LOG_FILE_MAX_BYTES", "10485760")),
            "backupCount": int(os.getenv("OVERLAY_LOG_FILE_BACKUP_COUNT", "5")),
            "encoding": "utf-8",
        }

    try:
        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "standard": {
                        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        "datefmt": "%Y-%m-%d %H:%M:%S",
                    }
                },
                "handlers": handlers,
                "root": {
                    "level": level,
                    "handlers": list(handlers),
                },
            }
        )
    except Exception:
        # Don't fail the app if file logging misconfigures; fall back to console only.
        handlers.pop("file", None)
        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "standard": {
                        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        "datefmt": "%Y-%m-%d %H:%M:%S",
                    }
                },
                "handlers": {"console": handlers["console"]},
                "root": {"level": level, "handlers": ["console"]},
            }
        )
        logging.getLogger(__name__).exception(
            "Failed to set up file logging; continuing with console only."
        )
