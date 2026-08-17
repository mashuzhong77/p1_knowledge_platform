"""认证：bcrypt 密码、DB 会话表、RBAC 操作权限。"""

import hashlib
import hmac
import secrets
import time

import bcrypt
from fastapi import Depends, Header, HTTPException

from .config import settings
from .database import get_connection
from .utils import now_iso

BCRYPT_PREFIX = "$2"
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_BYTES = 72  # bcrypt 的 72 字节上限


def hash_password(password: str, salt: str | None = None) -> str:
    """bcrypt；salt 参数仅为兼容旧调用方保留，被忽略。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored: str) -> bool:
    """兼容两种格式：bcrypt($2b$...) 或遗留 sha256({salt}${hexdigest})。"""
    if stored.startswith(BCRYPT_PREFIX):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except ValueError:  # 超过 72 字节或损坏哈希
            return False
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(
        hashlib.sha256((salt + password).encode("utf-8")).hexdigest(), digest
    )


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(BCRYPT_PREFIX)


def validate_new_password(new_password: str, current_password: str) -> str | None:
    """返回错误消息；合法返回 None。"""
    if len(new_password) < MIN_PASSWORD_LEN:
        return f"密码长度至少 {MIN_PASSWORD_LEN} 位"
    if len(new_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"密码过长（最多 {MAX_PASSWORD_BYTES} 字节）"
    if new_password == current_password:
        return "新密码不能与当前密码相同"
    return None


def roles_of(conn, user_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT r.role_code FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=?",
        (user_id,),
    ).fetchall()
    return [r["role_code"] for r in rows]


def permissions_of(conn, user_id: int) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT rp.permission_code FROM role_permissions rp
           JOIN user_roles ur ON ur.role_id=rp.role_id WHERE ur.user_id=?""",
        (user_id,),
    ).fetchall()
    return [r["permission_code"] for r in rows]


def _user_dict(conn, row) -> dict:
    user = dict(row)
    # 剥掉 get_current_user JOIN 引入的 _ 前缀内部别名（如 _session_expires）
    for key in [k for k in user if k.startswith("_")]:
        user.pop(key)
    user["roles"] = roles_of(conn, user["id"])
    user["role_code"] = user["roles"][0] if user["roles"] else None
    user["permissions"] = permissions_of(conn, user["id"])
    return user


# ---- 会话（auth_sessions 表，token 仅存 sha256） ----


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip()


def purge_expired_sessions(conn) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (time.time(),))


def login(username: str, password: str) -> dict | None:
    """校验密码；成功后发 DB 会话 token。遗留 sha256 哈希在本次登录成功时透明升级为 bcrypt。"""
    with get_connection() as conn:  # sqlite3 ctx manager 退出即提交
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND status='active'", (username,)
        ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        if needs_rehash(row["password_hash"]):
            conn.execute(
                "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                (hash_password(password), now_iso(), row["id"]),
            )
            row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
        user = _user_dict(conn, row)
        purge_expired_sessions(conn)
        token = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO auth_sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
            (_token_hash(token), user["id"], time.time() + settings.session_ttl_seconds, now_iso()),
        )
    return {
        "token": token,
        "user_info": user,
        "permissions": user["permissions"],
        "must_change_password": bool(user.get("must_change_password")),
    }


def get_current_user(token: str | None) -> dict | None:
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute(
            """SELECT u.*, s.expires_at AS _session_expires
               FROM auth_sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ?""",
            (_token_hash(token),),
        ).fetchone()
        if row is None or row["_session_expires"] < time.time():
            return None
        if row["status"] != "active":  # 停用即失效：删除该用户全部会话
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["id"],))
            return None
        return _user_dict(conn, row)


def logout(token: str | None) -> bool:
    if not token:
        return False
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_hash(token),))
        return cur.rowcount > 0


def check_current_password(user_id: int, password: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            return False
        return verify_password(password, row["password_hash"])


def change_password(user_id: int, new_password: str, keep_token: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?",
            (hash_password(new_password), now_iso(), user_id),
        )
        if keep_token:
            conn.execute(
                "DELETE FROM auth_sessions WHERE user_id=? AND token_hash <> ?",
                (user_id, _token_hash(keep_token)),
            )
        else:
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))


# ---- FastAPI 依赖 ----


def _resolve_token(authorization: str | None) -> dict:
    token = _bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="未登录")
    user = get_current_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="登录态失效")
    return user


def require_user(authorization: str | None = Header(default=None)) -> dict:
    """业务路由依赖：已登录且已通过首次改密门控。"""
    user = _resolve_token(authorization)
    if user.get("must_change_password"):
        raise HTTPException(
            status_code=403,
            detail={"code": "must_change_password", "message": "请先修改初始密码"},
        )
    return user


def require_session(authorization: str | None = Header(default=None)) -> dict:
    """认证豁免端点依赖（/me、/logout、/change-password）：已登录即可，不强制改密。"""
    return _resolve_token(authorization)


def require_admin(user: dict = Depends(require_user)) -> dict:
    if "admin" not in user.get("roles", []):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def has_permission(user: dict, code: str) -> bool:
    return "admin" in user.get("roles", []) or code in user.get("permissions", [])
