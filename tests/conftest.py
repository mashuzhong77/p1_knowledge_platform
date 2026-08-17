"""pytest 公共配置：保证从任意目录运行都能导入 app 包。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.utils import now_iso  # noqa: E402


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """使用临时 SQLite 数据库，避免污染工作区数据。"""
    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(settings, "db_path", db_path)
    init_db()
    return db_path


@pytest.fixture()
def client(db):
    """TestClient 包装应用；依赖 db fixture 的临时库。"""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_user():
    """构造用户（含角色绑定）的助手；接收已打开的 sqlite3 连接。返回 user_id。"""

    def _make(
        conn,
        username="tester",
        password="secret123",
        must_change=0,
        status="active",
        role_code="viewer",
    ) -> int:
        now = now_iso()
        role = conn.execute("SELECT id FROM roles WHERE role_code=?", (role_code,)).fetchone()
        role_id = role["id"] if role else conn.execute(
            "INSERT INTO roles(role_name,role_code,description) VALUES(?,?,?)",
            (role_code, role_code, ""),
        ).lastrowid
        uid = conn.execute(
            "INSERT INTO users(username,password_hash,display_name,department_id,status,must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (username, hash_password(password), username, None, status, must_change, now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO user_roles(user_id,role_id,created_at) VALUES(?,?,?)",
            (uid, role_id, now),
        )
        return uid

    return _make
