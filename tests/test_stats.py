"""看板统计：访问次数、独立人数、热门问题与响应趋势。"""

from app.stats import aggregate_stats


def test_aggregate_stats_counts_and_ranks():
    access_rows = [
        {"user_id": 1, "unit_id": 10},
        {"user_id": 1, "unit_id": 10},
        {"user_id": 2, "unit_id": 11},
    ]
    faq_rows = [
        {"question": "什么是双碳？", "hit_count": 5},
        {"question": "什么是绿建？", "hit_count": 9},
    ]
    latency_rows = [
        {"date": "2026-08-16", "latency_ms": 800},
        {"date": "2026-08-16", "latency_ms": 1200},
    ]
    stats = aggregate_stats(
        access_rows=access_rows,
        unit_count=42,
        faq_rows=faq_rows,
        latency_rows=latency_rows,
        token_total=1234,
    )
    assert stats["total_accesses"] == 3
    assert stats["unique_users"] == 2
    assert stats["knowledge_unit_count"] == 42
    assert stats["top_questions"][0]["question"] == "什么是绿建？"
    assert stats["hot_units"][0]["unit_id"] == 10
    assert stats["token_consumption"] == 1234
    assert stats["response_time_trend"][0]["avg_ms"] == 1000
