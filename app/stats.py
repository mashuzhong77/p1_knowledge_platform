"""数据看板统计聚合。"""

import json
from collections import Counter, defaultdict

from .database import get_connection


def _ids(value: str) -> list[int]:
    try:
        return [int(x) for x in json.loads(value or "[]")]
    except Exception:  # noqa: BLE001
        return []


def _latency_trend(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        groups[r["date"]].append(r["latency_ms"])
    return [
        {"date": d, "avg_ms": round(sum(v) / len(v))} for d, v in sorted(groups.items())
    ]


def aggregate_stats(
    access_rows: list[dict],
    unit_count: int,
    faq_rows: list[dict],
    latency_rows: list[dict],
    token_total: int,
) -> dict:
    hot = Counter(r["unit_id"] for r in access_rows).most_common(5)
    return {
        "total_accesses": len(access_rows),
        "unique_users": len({r["user_id"] for r in access_rows}),
        "knowledge_unit_count": unit_count,
        "top_questions": sorted(faq_rows, key=lambda r: r["hit_count"], reverse=True)[:5],
        "hot_units": [{"unit_id": u, "access_count": c} for u, c in hot],
        "token_consumption": token_total,
        "response_time_trend": _latency_trend(latency_rows),
    }


def dashboard_stats() -> dict:
    with get_connection() as conn:
        log_rows = conn.execute(
            "SELECT user_id, authorized_unit_ids_json, created_at, response_time_ms FROM qa_access_logs"
        ).fetchall()
        access_rows = [
            {"user_id": r["user_id"], "unit_id": u, "date": r["created_at"][:10], "latency_ms": r["response_time_ms"]}
            for r in log_rows
            for u in _ids(r["authorized_unit_ids_json"])
        ]
        latency_rows = [
            {"date": r["created_at"][:10], "latency_ms": r["response_time_ms"]} for r in log_rows
        ]
        faq_rows = [
            {"question": r["question"], "hit_count": r["hit_count"]}
            for r in conn.execute("SELECT question, hit_count FROM faqs").fetchall()
        ]
        token_total = conn.execute(
            "SELECT COALESCE(SUM(total_tokens),0) t FROM qa_access_logs"
        ).fetchone()["t"]
        unit_count = conn.execute(
            "SELECT COUNT(*) c FROM knowledge_units WHERE status!='archived'"
        ).fetchone()["c"]
    return aggregate_stats(access_rows, unit_count, faq_rows, latency_rows, token_total)


def hot_units_with_titles() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title FROM knowledge_units"
        ).fetchall()
        title_map = {r["id"]: r["title"] for r in rows}
        counts: Counter = Counter()
        for r in conn.execute("SELECT authorized_unit_ids_json FROM qa_access_logs").fetchall():
            for uid in _ids(r["authorized_unit_ids_json"]):
                counts[uid] += 1
    return [
        {"unit_id": uid, "title": title_map.get(uid, ""), "access_count": c}
        for uid, c in counts.most_common(5)
    ]
