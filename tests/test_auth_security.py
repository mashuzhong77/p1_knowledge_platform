"""P0 安全测试：bcrypt / 会话表 / 强制改密门控 / 上传守卫 / 安全头。"""

import hashlib
import io
from pathlib import Path

import pytest

import app.ratelimit as ratelimit
from app.auth import get_current_user, hash_password, needs_rehash, verify_password
from app.config import settings
from app.database import get_connection
from app.utils import now_iso

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    ratelimit._BUCKETS.clear()
    yield
    ratelimit._BUCKETS.clear()


@pytest.fixture()
def tmp_upload(monkeypatch, tmp_path):
    """上传落盘与向量目录指向临时目录，避免污染工作区 data/。"""
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vectors")
    return tmp_path / "uploads"


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _auth(client, username="admin", password="secret123"):
    r = _login(client, username, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _upload(client, headers, filename, content, content_type="text/markdown"):
    return client.post(
        "/api/knowledge/import",
        headers=headers,
        files={"files": (filename, io.BytesIO(content), content_type)},
        data={"security_level": "internal"},
    )


# ---- 哈希与兼容 ----


def test_hash_password_is_bcrypt_and_roundtrip():
    h = hash_password("secret123")
    assert h.startswith("$2")
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_legacy_sha256_verify_and_auto_rehash(db, client):
    # 手工构造遗留 sha256 {salt}${digest}
    salt = "testsalt"
    digest = hashlib.sha256((salt + "oldpass").encode("utf-8")).hexdigest()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users(username,password_hash,display_name,status,must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            ("legacyuser", f"{salt}${digest}", "遗留用户", "active", 0, now_iso(), now_iso()),
        )

    # 登录成功 → 返回 must_change_password=false
    r = _login(client, "legacyuser", "oldpass")
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False

    # DB 中哈希已透明升级为 bcrypt
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username=?", ("legacyuser",)
        ).fetchone()
        assert row["password_hash"].startswith("$2")
        assert needs_rehash(row["password_hash"]) is False

    # 升级后用同一密码仍可登录
    assert _login(client, "legacyuser", "oldpass").status_code == 200


# ---- 会话表 ----


def test_login_creates_session_row(db, client, make_user):
    with get_connection() as conn:
        uid = make_user(conn, username="sessionuser", role_code="viewer")
    r = _login(client, "sessionuser", "secret123")
    assert r.status_code == 200
    token = r.json()["token"]

    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c FROM auth_sessions WHERE user_id=?", (uid,)
        ).fetchone()
        assert row["c"] == 1
        expires = conn.execute(
            "SELECT expires_at FROM auth_sessions WHERE user_id=?", (uid,)
        ).fetchone()
        assert expires["expires_at"] > 0

    # get_current_user 返回完整 shape（含 must_change_password）
    user = get_current_user(token)
    assert user["id"] == uid
    assert user["username"] == "sessionuser"
    assert user["role_code"] == "viewer"
    assert "must_change_password" in user


def test_logout_revokes_session(db, client, make_user):
    with get_connection() as conn:
        make_user(conn, username="lo", role_code="viewer")
    h = _auth(client, "lo")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401
    # 幂等：二次登出仍 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200


def test_disabled_user_session_invalidated(db, client, make_user):
    with get_connection() as conn:
        uid = make_user(conn, username="dis", role_code="viewer")
    h = _auth(client, "dis")
    assert client.get("/api/auth/me", headers=h).status_code == 200

    with get_connection() as conn:
        conn.execute("UPDATE users SET status='disabled' WHERE id=?", (uid,))
    assert client.get("/api/auth/me", headers=h).status_code == 401
    with get_connection() as conn:
        c = conn.execute(
            "SELECT COUNT(*) c FROM auth_sessions WHERE user_id=?", (uid,)
        ).fetchone()["c"]
        assert c == 0


# ---- 强制改密门控 ----


def test_must_change_password_gate(db, client, make_user):
    with get_connection() as conn:
        make_user(conn, username="must", must_change=1, role_code="admin")
    r = _login(client, "must", "secret123")
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True
    h = {"Authorization": f"Bearer {r.json()['token']}"}

    # 豁免端点 /me 可用
    assert client.get("/api/auth/me", headers=h).status_code == 200
    # 业务接口被门控：403 + code
    r2 = client.get("/api/knowledge/units", headers=h)
    assert r2.status_code == 403
    assert r2.json()["detail"]["code"] == "must_change_password"

    # 改密成功（保留当前会话）
    r3 = client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "secret123", "new_password": "newsecret123"},
    )
    assert r3.status_code == 200
    # 门控解除，业务可用
    assert client.get("/api/knowledge/units", headers=h).status_code == 200


def test_change_password_policy(db, client, make_user):
    with get_connection() as conn:
        make_user(conn, username="cp", role_code="viewer")
    h = _auth(client, "cp")

    # 密码过短
    r = client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "secret123", "new_password": "short"},
    )
    assert r.status_code == 400
    # 与当前密码相同
    r = client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "secret123", "new_password": "secret123"},
    )
    assert r.status_code == 400
    # 当前密码错误
    r = client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "wrong", "new_password": "newsecret123"},
    )
    assert r.status_code == 400

    # 合法改密 → 旧密码失效、新密码可登录
    r = client.post(
        "/api/auth/change-password", headers=h,
        json={"current_password": "secret123", "new_password": "newsecret123"},
    )
    assert r.status_code == 200
    assert _login(client, "cp", "secret123").status_code == 401
    assert _login(client, "cp", "newsecret123").status_code == 200


# ---- 上传守卫 ----


def test_upload_rejects_path_traversal(db, client, make_user, tmp_upload):
    with get_connection() as conn:
        make_user(conn, username="adm", role_code="admin")
    h = _auth(client, "adm")

    r = _upload(client, h, "..\\..\\..\\evil.md", "# 遍历测试\n内容。".encode("utf-8"))
    # 安全落盘：200 且文件落在临时 upload_dir，项目根目录无穿越文件
    assert r.status_code == 200, r.text
    saved = list(tmp_upload.glob("*.md"))
    assert saved, "应有安全落盘文件"
    assert all(f.name.startswith("upload_") or "evil.md" in f.name for f in saved)
    assert not (PROJECT_ROOT / "evil.md").exists()


def test_upload_rejects_bad_extension(db, client, make_user, tmp_upload):
    with get_connection() as conn:
        make_user(conn, username="adm3", role_code="admin")
    h = _auth(client, "adm3")
    r = _upload(client, h, "evil.exe", b"MZ", "application/octet-stream")
    assert r.status_code == 400
    assert list(tmp_upload.glob("*")) == []


def test_upload_size_limit(db, client, make_user, tmp_upload, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    with get_connection() as conn:
        make_user(conn, username="adm2", role_code="admin")
    h = _auth(client, "adm2")
    big = b"x" * (1024 * 1024 + 512)
    r = _upload(client, h, "big.txt", big, "text/plain")
    assert r.status_code == 413
    assert list(tmp_upload.glob("*")) == []  # 无残留


# ---- 安全头 ----


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert r.headers.get("x-xss-protection") == "0"
    csp = r.headers.get("content-security-policy", "")
    assert "unsafe-inline" in csp
    assert "frame-ancestors 'none'" in csp
    # 默认 force_https_headers=false，无 HSTS
    assert r.headers.get("strict-transport-security") is None


def test_hsts_header_when_forced(client, monkeypatch):
    monkeypatch.setattr(settings, "force_https_headers", True)
    r = client.get("/health")
    assert r.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
