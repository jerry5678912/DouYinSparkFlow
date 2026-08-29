import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

LOG_FILE = "logs/app.log"
RELIABILITY_FIELDS = {
    "run_id",
    "account",
    "account_count",
    "attempt",
    "attempts",
    "target_count",
    "remaining_count",
    "verified_count",
    "failed_count",
    "completed_account_count",
    "duration_ms",
    "outcome",
    "error_type",
}


class JsonFormatter(logging.Formatter):
    """Emit bounded structured logs that Cloud Logging can query safely."""

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log_message"),
            "message": record.getMessage(),
            "source": f"{record.filename}:{record.lineno}",
        }
        for field in RELIABILITY_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def resolve_log_level(level):
    if isinstance(level, int):
        return level

    if isinstance(level, str):
        mapping = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }
        return mapping.get(level.lower(), logging.INFO)

    return logging.INFO


def setup_logger(name="app", level="Info"):
    resolved_level = resolve_log_level(level)
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(resolved_level)
    logger.propagate = False

    formatter = JsonFormatter()

    if not logger.handlers:
        console_handler = logging.StreamHandler()
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    for handler in logger.handlers:
        handler.setLevel(resolved_level)
        handler.setFormatter(formatter)

    return logger


if __name__ == "__main__":
    logger = setup_logger(level="Debug")
    logger.debug("这是一个调试信息")
    logger.info("这是一个普通信息")
    logger.warning("这是一个警告信息")
    logger.error("这是一个错误信息")
    logger.critical("这是一个严重错误信息")
