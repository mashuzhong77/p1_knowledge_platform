"""知识沉淀：FAQ 挖掘/审核/缓存、反馈闭环、知识缺口。"""

import json

from .database import get_connection
from .utils import now_iso

FAQ_CACHE: dict[str, str] = {}


def upsert_gap(conn, question: str) -> None:
    q = (question or "").strip()[:100]
    row = conn.execute(
        "SELECT id, ask_count FROM knowledge_gaps WHERE question_pattern=?", (q,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE knowledge_gaps SET ask_count=ask_count+1, last_asked_at=? WHERE id=?",
            (now_iso(), row["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO knowledge_gaps(question_pattern,sample_questions_json,ask_count,last_asked_at,status,created_at)
               VALUES(?,?,?,?,?,?)""",
            (q, json.dumps([question], ensure_ascii=False), 1, now_iso(), "unresolved", now_iso()),
        )


def mine_faq(min_count: int = 2) -> list[dict]:
    now = now_iso()
    out: list[dict] = []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT question, COUNT(*) c FROM qa_access_logs GROUP BY question HAVING c>=? ORDER BY c DESC",
            (min_count,),
        ).fetchall()
        for r in rows:
            cur = conn.execute("SELECT id FROM faqs WHERE question=?", (r["question"],)).fetchone()
            if cur:
                conn.execute("UPDATE faqs SET hit_count=? WHERE id=?", (r["c"], cur["id"]))
                out.append({"id": cur["id"], "question": r["question"], "c": r["c"]})
            else:
                c = conn.execute(
                    """INSERT INTO faqs(question,answer,category,source_type,status,hit_count,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (r["question"], "", "", "auto_mined", "pending_review", r["c"], now, now),
                )
                out.append({"id": c.lastrowid, "question": r["question"], "c": r["c"]})
    return out


def publish_faq(faq_id: int, answer: str, reviewer_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE faqs SET answer=?, status='published', reviewer_id=?, reviewed_at=? WHERE id=?",
            (answer, reviewer_id, now_iso(), faq_id),
        )
        row = conn.execute("SELECT question, answer FROM faqs WHERE id=?", (faq_id,)).fetchone()
        if row:
            FAQ_CACHE[row["question"]] = row["answer"]


def reject_faq(faq_id: int, reviewer_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE faqs SET status='rejected', reviewer_id=?, reviewed_at=? WHERE id=?",
            (reviewer_id, now_iso(), faq_id),
        )


def get_faq_answer(question: str) -> str | None:
    if question in FAQ_CACHE:
        with get_connection() as conn:
            conn.execute("UPDATE faqs SET hit_count=hit_count+1 WHERE question=?", (question,))
        return FAQ_CACHE[question]
    with get_connection() as conn:
        row = conn.execute(
            "SELECT answer FROM faqs WHERE question=? AND status='published'", (question,)
        ).fetchone()
        if row:
            FAQ_CACHE[question] = row["answer"]
            conn.execute("UPDATE faqs SET hit_count=hit_count+1 WHERE question=?", (question,))
            return row["answer"]
    return None


def list_recommendations() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM faqs WHERE status='pending_review' ORDER BY hit_count DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def record_feedback(data: dict, user_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO qa_feedback(session_id,user_id,question,answer,rating,feedback_type,comment,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                data.get("session_id", ""),
                user_id,
                data.get("question", ""),
                data.get("answer", ""),
                data.get("rating", "up"),
                data.get("feedback_type", "none"),
                data.get("comment", ""),
                now_iso(),
            ),
        )


def list_gaps() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM knowledge_gaps ORDER BY ask_count DESC").fetchall()
    return [dict(r) for r in rows]
