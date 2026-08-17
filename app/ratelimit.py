"""滑动窗口限流（框架 R9，蒸馏自 ai_0302 rate_limit_utils）。"""

import time
from collections import deque

_TIMESTAMPS: deque = deque()
# 命名桶：不同接口独立限流窗口；_default 复用 _TIMESTAMPS（兼容既有测试）
_BUCKETS: dict[str, deque] = {"_default": _TIMESTAMPS}


def apply_rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    bucket: str = "_default",
) -> None:
    """窗口内请求数达上限则阻塞等待窗口滑动；默认 60 次/60s。"""
    q = _BUCKETS.setdefault(bucket, deque())
    now = time.time()
    while q and now - q[0] >= window_seconds:
        q.popleft()
    if len(q) >= max_requests:
        sleep_for = window_seconds - (now - q[0])
        if sleep_for > 0:
            time.sleep(sleep_for)
            now = time.time()
            while q and now - q[0] >= window_seconds:
                q.popleft()
    q.append(time.time())
