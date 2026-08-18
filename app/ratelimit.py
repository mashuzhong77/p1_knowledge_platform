"""滑动窗口限流（per-key，支持按 IP / 用户名 / 命名桶隔离）。"""

import time
from collections import deque

from fastapi import HTTPException, Request

# key → deque of timestamps；每个 key 独立滑动窗口
_BUCKETS: dict[str, deque] = {}


def _client_ip(request: Request) -> str:
    """从 Request 提取客户端 IP（优先 X-Forwarded-For，兼容反代）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    key: str,
    max_requests: int = 10,
    window_seconds: int = 60,
) -> None:
    """检查指定 key 是否超过窗口上限，超过则抛 429。"""
    q = _BUCKETS.setdefault(key, deque())
    now = time.time()
    while q and now - q[0] >= window_seconds:
        q.popleft()
    if len(q) >= max_requests:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    q.append(now)


def apply_rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    bucket: str = "_default",
) -> None:
    """兼容旧调用的全局桶限流（保留不改密码等场景）。"""
    check_rate_limit(bucket, max_requests, window_seconds)
