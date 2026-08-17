"""结构化日志（框架 R9，蒸馏自 ai_0302 logger）：loguru 按天轮转，缺失时回退 logging。"""

from .config import settings

LOG_DIR = settings.db_path.parent / "logs"


def get_logger(name: str = "p1"):
    try:
        from loguru import logger

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.add(
            LOG_DIR / "app_{time:YYYYMMDD}.log",
            level="INFO",
            rotation="00:00",
            retention="7 days",
            encoding="utf-8",
            enqueue=True,
        )
        return logger
    except Exception:  # noqa: BLE001
        import logging

        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)


logger = get_logger()
