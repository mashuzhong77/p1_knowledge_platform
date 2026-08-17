"""任务进度：状态流转、节点中文映射、状态查询接口。"""

from app.auth import hash_password
from app.database import db
from app.tasks import (
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    add_done_task,
    create_task,
    get_task,
    update_task_status,
)
from app.utils import now_iso


def test_task_registry_status_transitions():
    create_task("t1")
    assert get_task("t1")["status"] == STATUS_PENDING
    update_task_status("t1", STATUS_PROCESSING)
    add_done_task("t1", "upload_file")
    add_done_task("t1", "import")
    update_task_status("t1", STATUS_COMPLETED)
    task = get_task("t1")
    assert task["status"] == STATUS_COMPLETED
    assert task["done_list"] == ["上传文件", "导入入库"]


def test_task_registry_missing_returns_none():
    assert get_task("not-exist") is None


def _seed_admin():
    now = now_iso()
    with db() as conn:
        role_id = conn.execute(
            "INSERT INTO roles(role_name,role_code,description) VALUES(?,?,?)",
            ("系统管理员", "admin", ""),
        ).lastrowid
        uid = conn.execute(
            "INSERT INTO users(username,password_hash,display_name,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("admin", hash_password("admin123"), "管理员", "active", now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO user_roles(user_id,role_id,created_at) VALUES(?,?,?)",
            (uid, role_id, now),
        )


def test_import_status_endpoint(db):
    _seed_admin()
    from fastapi.testclient import TestClient

    from app.main import app

    create_task("t-route")
    with TestClient(app) as c:
        token = c.post(
            "/api/auth/login", json={"username": "admin", "password": "admin123"}
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = c.get("/api/knowledge/import/status/t-route", headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

        r2 = c.get("/api/knowledge/import/status/not-exist", headers=headers)
        assert r2.status_code == 404
