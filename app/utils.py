"""通用工具函数。"""

from datetime import datetime


def now_iso() -> str:
    """返回当前时间的 ISO 字符串（秒级精度）。"""
    return datetime.now().isoformat(timespec="seconds")
