"""限流：窗口内超限抛 429。"""

import pytest

import app.ratelimit as ratelimit
from fastapi import HTTPException


def test_rate_limit_rejects_after_limit():
    ratelimit._BUCKETS.clear()

    # 前 3 次通过
    for _ in range(3):
        ratelimit.apply_rate_limit(max_requests=3, window_seconds=60)

    # 第 4 次抛 429
    with pytest.raises(HTTPException) as exc_info:
        ratelimit.apply_rate_limit(max_requests=3, window_seconds=60)
    assert exc_info.value.status_code == 429

    ratelimit._BUCKETS.clear()


def test_per_key_isolation():
    """不同 key 独立计数，互不影响。"""
    ratelimit._BUCKETS.clear()

    ratelimit.check_rate_limit("a", max_requests=2, window_seconds=60)
    ratelimit.check_rate_limit("a", max_requests=2, window_seconds=60)
    with pytest.raises(HTTPException):
        ratelimit.check_rate_limit("a", max_requests=2, window_seconds=60)

    # key "b" 不受 "a" 影响
    ratelimit.check_rate_limit("b", max_requests=2, window_seconds=60)

    ratelimit._BUCKETS.clear()
