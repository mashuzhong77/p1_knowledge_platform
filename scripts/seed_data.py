"""种子数据：演示账号 + 示例语料入库（python scripts/seed_data.py）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import db, init_db  # noqa: E402
from app.knowledge.crud import publish_unit  # noqa: E402
from app.knowledge.fts import FtsStore  # noqa: E402
from app.knowledge.importer import import_text  # noqa: E402
from app.utils import now_iso  # noqa: E402

DEPARTMENTS = [("总部", None), ("技术部", None), ("工程部", None)]
ROLES = [
    ("admin", "系统管理员", "全部权限"),
    ("editor", "知识管理员", "知识维护 + 问答 + 看板"),
    ("viewer", "普通用户", "查看 + 问答"),
]
PERMS = {
    "admin": [
        "knowledge:view", "knowledge:edit", "knowledge:import", "knowledge:delete",
        "knowledge:permission", "knowledge:confidential", "ai:chat", "dashboard:view", "faq:review", "audit:view",
    ],
    "editor": ["knowledge:view", "knowledge:edit", "knowledge:import", "knowledge:permission", "ai:chat", "dashboard:view"],
    "viewer": ["knowledge:view", "ai:chat"],
}
USERS = [
    ("admin", "admin123", "系统管理员", 0, "admin"),
    ("editor", "123456", "知识管理员", 1, "editor"),
    ("viewer", "123456", "普通用户", 2, "viewer"),
]

# 默认置 must_change_password=1（首次登录强制改密）；--no-force-change 供 CI/e2e 旁路
FORCE_CHANGE = "--no-force-change" not in sys.argv


def seed() -> None:
    init_db()
    now = now_iso()
    with db() as conn:
        dept_ids = []
        for name, parent in DEPARTMENTS:
            row = conn.execute("SELECT id FROM departments WHERE name=?", (name,)).fetchone()
            if row:
                dept_ids.append(row["id"])
            else:
                dept_ids.append(
                    conn.execute(
                        "INSERT INTO departments(name,parent_id,sort_order,created_at) VALUES(?,?,?,?)",
                        (name, parent, len(dept_ids), now),
                    ).lastrowid
                )
        role_ids = {}
        for code, name, desc in ROLES:
            row = conn.execute("SELECT id FROM roles WHERE role_code=?", (code,)).fetchone()
            role_ids[code] = row["id"] if row else conn.execute(
                "INSERT INTO roles(role_name,role_code,description) VALUES(?,?,?)", (name, code, desc)
            ).lastrowid
        for code, perms in PERMS.items():
            conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_ids[code],))
            for p in perms:
                conn.execute(
                    "INSERT INTO role_permissions(role_id,permission_code,permission_type,created_at) VALUES(?,?,?,?)",
                    (role_ids[code], p, "button", now),
                )
        force = 1 if FORCE_CHANGE else 0
        for username, pw, disp, dept_idx, role in USERS:
            row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if row:
                uid = row["id"]
                # 已存在的种子账号：只置强制改密标记，不覆盖密码（密码按需由用户自行修改）
                conn.execute(
                    "UPDATE users SET must_change_password=?, updated_at=? WHERE id=?",
                    (force, now, uid),
                )
            else:
                uid = conn.execute(
                    "INSERT INTO users(username,password_hash,display_name,department_id,status,must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (username, hash_password(pw), disp, dept_ids[dept_idx], "active", force, now, now),
                ).lastrowid
            conn.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
            conn.execute(
                "INSERT INTO user_roles(user_id,role_id,created_at) VALUES(?,?,?)",
                (uid, role_ids[role], now),
            )

    kb = settings.knowledge_dir
    kb.mkdir(parents=True, exist_ok=True)
    total = 0
    for path in sorted(kb.glob("*.md")):
        with db() as conn:
            exists = conn.execute(
                "SELECT COUNT(*) c FROM knowledge_units WHERE source_file_name=?", (path.name,)
            ).fetchone()["c"]
        if exists:
            print(f"skip（已存在）: {path.name}")
            continue
        result = import_text(
            title=path.stem,
            content=path.read_text(encoding="utf-8"),
            creator_id=1,
            security_level="internal",
            data_domain="绿建/双碳",
            scope=[{"target_type": "global", "target_id": None}],
            source_file_name=path.name,
            file_type="md",
            file_size=path.stat().st_size,
        )
        with db() as conn:
            for uid in result["unit_ids"]:
                publish_unit(conn, uid, reviewer_id=1)
        total += result["imported"]
    with db() as conn:
        FtsStore.rebuild(conn)
    print(f"seed OK: 用户=3, 知识单元={total}, must_change_password={'1' if FORCE_CHANGE else '0'}")


if __name__ == "__main__":
    seed()
