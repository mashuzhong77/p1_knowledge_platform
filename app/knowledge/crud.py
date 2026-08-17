"""知识单元 CRUD、四类数据权限、版本与发布管理。"""

import difflib
import secrets
import time

from ..permissions import unit_allows
from ..utils import now_iso
from .fts import FtsStore


def _unit_code() -> str:
    return f"U{int(time.time() * 1000)}{secrets.token_hex(2)}"


def create_unit(
    conn,
    *,
    title: str,
    content: str,
    summary: str = "",
    category: str = "",
    source_file_name: str = "",
    file_type: str = "",
    file_size: int = 0,
    security_level: str = "internal",
    data_domain: str = "",
    creator_id: int,
    status: str = "draft",
) -> int:
    now = now_iso()
    cur = conn.execute(
        """INSERT INTO knowledge_units
           (unit_code,title,content,summary,category,source_file_name,file_type,file_size,status,
            version_no,parent_id,security_level,data_domain,creator_id,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            _unit_code(),
            title,
            content,
            summary,
            category,
            source_file_name,
            file_type,
            file_size,
            status,
            1,
            None,
            security_level,
            data_domain,
            creator_id,
            now,
            now,
        ),
    )
    unit_id = cur.lastrowid
    FtsStore.sync_unit(conn, unit_id)
    return unit_id


def _row(conn, unit_id: int):
    return conn.execute("SELECT * FROM knowledge_units WHERE id=?", (unit_id,)).fetchone()


def chain_ids(conn, unit_id: int) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    cur_id = unit_id
    while cur_id and cur_id not in seen:
        seen.add(cur_id)
        ids.append(cur_id)
        r = conn.execute("SELECT parent_id FROM knowledge_units WHERE id=?", (cur_id,)).fetchone()
        cur_id = r["parent_id"] if r else None
    frontier = list(ids)
    while frontier:
        marks = ",".join("?" * len(frontier))
        rows = conn.execute(f"SELECT id FROM knowledge_units WHERE parent_id IN ({marks})", frontier).fetchall()
        frontier = [r["id"] for r in rows if r["id"] not in seen]
        for i in frontier:
            seen.add(i)
            ids.append(i)
    return ids


def max_version_no(conn, unit_id: int) -> int:
    ids = chain_ids(conn, unit_id)
    if not ids:
        return 1
    marks = ",".join("?" * len(ids))
    row = conn.execute(f"SELECT MAX(version_no) m FROM knowledge_units WHERE id IN ({marks})", ids).fetchone()
    return row["m"] or 1


def list_versions(conn, unit_id: int) -> list[dict]:
    ids = chain_ids(conn, unit_id)
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM knowledge_units WHERE id IN ({marks}) ORDER BY version_no", ids
    ).fetchall()
    return [dict(r) for r in rows]


def update_unit_content(conn, unit_id: int, new_content: str, user_id: int | None = None, **fields) -> int:
    row = _row(conn, unit_id)
    if row is None:
        raise ValueError("unit not found")
    now = now_iso()
    if row["status"] in ("published", "archived"):
        vno = max_version_no(conn, unit_id) + 1
        cur = conn.execute(
            """INSERT INTO knowledge_units
               (unit_code,title,content,summary,category,source_file_name,file_type,file_size,status,
                version_no,parent_id,security_level,data_domain,creator_id,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _unit_code(),
                fields.get("title", row["title"]),
                new_content,
                fields.get("summary", row["summary"]),
                fields.get("category", row["category"]),
                row["source_file_name"],
                row["file_type"],
                row["file_size"],
                "draft",
                vno,
                unit_id,
                row["security_level"],
                row["data_domain"],
                user_id or row["creator_id"],
                now,
                now,
            ),
        )
        new_id = cur.lastrowid
        FtsStore.sync_unit(conn, new_id)
        return new_id
    conn.execute(
        "UPDATE knowledge_units SET content=?, summary=?, category=?, updated_at=? WHERE id=?",
        (
            new_content,
            fields.get("summary", row["summary"]),
            fields.get("category", row["category"]),
            now,
            unit_id,
        ),
    )
    FtsStore.sync_unit(conn, unit_id)
    return unit_id


def publish_unit(conn, unit_id: int, reviewer_id: int | None = None) -> None:
    conn.execute(
        "UPDATE knowledge_units SET status='published', reviewed_by=?, reviewed_at=? WHERE id=?",
        (reviewer_id, now_iso(), unit_id),
    )


def archive_unit(conn, unit_id: int) -> None:
    conn.execute("UPDATE knowledge_units SET status='archived', updated_at=? WHERE id=?", (now_iso(), unit_id))


def rollback_unit(conn, unit_id: int, target_version_id: int, user_id: int | None = None) -> int:
    cur = _row(conn, unit_id)
    target = _row(conn, target_version_id)
    if cur is None or target is None:
        raise ValueError("unit not found")
    vno = max_version_no(conn, unit_id) + 1
    now = now_iso()
    c = conn.execute(
        """INSERT INTO knowledge_units
           (unit_code,title,content,summary,category,source_file_name,file_type,file_size,status,
            version_no,parent_id,security_level,data_domain,creator_id,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            _unit_code(),
            target["title"],
            target["content"],
            target["summary"],
            target["category"],
            cur["source_file_name"],
            cur["file_type"],
            cur["file_size"],
            "draft",
            vno,
            unit_id,
            cur["security_level"],
            cur["data_domain"],
            user_id or cur["creator_id"],
            now,
            now,
        ),
    )
    new_id = c.lastrowid
    FtsStore.sync_unit(conn, new_id)
    return new_id


def content_diff(old: str, new: str) -> list[str]:
    return list(
        difflib.unified_diff(
            (old or "").splitlines(), (new or "").splitlines(), lineterm="", n=1
        )
    )


def get_unit_permissions(conn, unit_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT target_type, target_id FROM unit_permissions WHERE unit_id=?", (unit_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def set_unit_permissions(conn, unit_id: int, perms: list[dict]) -> None:
    conn.execute("DELETE FROM unit_permissions WHERE unit_id=?", (unit_id,))
    for p in perms:
        conn.execute(
            "INSERT INTO unit_permissions(unit_id,target_type,target_id,created_at) VALUES(?,?,?,?)",
            (unit_id, p.get("target_type"), str(p.get("target_id") or ""), now_iso()),
        )


def get_unit(conn, unit_id: int) -> dict | None:
    row = _row(conn, unit_id)
    if row is None:
        return None
    u = dict(row)
    u["perms"] = get_unit_permissions(conn, unit_id)
    return u


def list_units(conn, user: dict, category: str | None = None, status: str | None = None) -> list[dict]:
    rows = conn.execute("SELECT * FROM knowledge_units ORDER BY id DESC").fetchall()
    out: list[dict] = []
    for r in rows:
        u = dict(r)
        u["perms"] = get_unit_permissions(conn, r["id"])
        if not unit_allows(u, user):
            continue
        if category and u["category"] != category:
            continue
        if status and u["status"] != status:
            continue
        u.pop("perms", None)
        out.append(u)
    return out


def delete_units(conn, unit_ids: list[int]) -> list[str]:
    deleted: list[str] = []
    for uid in unit_ids:
        rows = conn.execute(
            "SELECT id FROM knowledge_units WHERE id=? OR parent_id=?", (uid, uid)
        ).fetchall()
        ids = [r["id"] for r in rows]
        deleted.extend(str(i) for i in ids)
        conn.execute(
            "DELETE FROM unit_permissions WHERE unit_id IN (SELECT id FROM knowledge_units WHERE id=? OR parent_id=?)",
            (uid, uid),
        )
        conn.execute("DELETE FROM knowledge_units WHERE id=? OR parent_id=?", (uid, uid))
    FtsStore.sync_delete(conn, deleted)
    return deleted
