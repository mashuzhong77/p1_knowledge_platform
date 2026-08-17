"""限流：窗口内超限阻塞等待。"""

import app.ratelimit as ratelimit


def test_rate_limit_blocks_after_limit(monkeypatch):
    sleeps = []
    monkeypatch.setattr(ratelimit.time, "sleep", lambda s: sleeps.append(s))
    ratelimit._TIMESTAMPS.clear()

    for _ in range(3):
        ratelimit.apply_rate_limit(max_requests=3, window_seconds=60)
    assert sleeps == []

    # 第 4 次请求触发阻塞等待
    ratelimit.apply_rate_limit(max_requests=3, window_seconds=60)
    assert len(sleeps) == 1
    assert sleeps[0] > 0
    ratelimit._TIMESTAMPS.clear()
