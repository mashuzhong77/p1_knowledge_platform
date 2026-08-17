"""审计日志：写操作留痕与查询。"""

import json

from .database import get_connection
from .utils import now_iso


def log_action(
    user_id: int,
    action: str,
    resource_type: str,
    resource_id,
    detail: dict | None = None,
    conn=None,
) -> None:
    params = (
        user_id,
        action,
        resource_type,
        str(resource_id),
        json.dumps(detail or {}, ensure_ascii=False),
        now_iso(),
    )
    if conn is not None:
        conn.execute(
            "INSERT INTO audit_logs(user_id,action,resource_type,resource_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            params,
        )
        return
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_logs(user_id,action,resource_type,resource_id,detail_json,created_at) VALUES(?,?,?,?,?,?)",
            params,
        )


def list_logs(user_id: int | None = None, action: str | None = None, limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    params: list = []
    if user_id:
        sql += " AND user_id=?"
        params.append(user_id)
    if action:
        sql += " AND action=?"
        params.append(action)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
