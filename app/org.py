"""组织架构：用户 / 部门 / 角色 / 权限码管理。"""

from .auth import hash_password, roles_of
from .database import get_connection
from .utils import now_iso


def list_departments() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM departments ORDER BY sort_order, id").fetchall()
    return [dict(r) for r in rows]


def list_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT u.id, u.username, u.display_name, u.department_id, u.status,
                      d.name AS department_name
               FROM users u LEFT JOIN departments d ON d.id=u.department_id
               ORDER BY u.id"""
        ).fetchall()
        users = []
        for r in rows:
            u = dict(r)
            u["roles"] = roles_of(conn, r["id"])
            users.append(u)
    return users


def create_user(
    username: str,
    password: str,
    display_name: str = "",
    department_id: int | None = None,
    role_codes: list[str] | None = None,
) -> int:
    now = now_iso()
    with get_connection() as conn:
        # 新账号 must_change_password=1：首次登录须自设密码
        cur = conn.execute(
            "INSERT INTO users(username,password_hash,display_name,department_id,status,must_change_password,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (username, hash_password(password), display_name, department_id, "active", 1, now, now),
        )
        user_id = cur.lastrowid
        for code in role_codes or []:
            role = conn.execute("SELECT id FROM roles WHERE role_code=?", (code,)).fetchone()
            if role:
                conn.execute(
                    "INSERT INTO user_roles(user_id,role_id,created_at) VALUES(?,?,?)",
                    (user_id, role["id"], now),
                )
    return user_id


def list_roles() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM roles ORDER BY id").fetchall()
        out = []
        for r in rows:
            role = dict(r)
            perms = conn.execute(
                "SELECT permission_code FROM role_permissions WHERE role_id=?", (r["id"],)
            ).fetchall()
            role["permissions"] = [p["permission_code"] for p in perms]
            out.append(role)
    return out


def set_role_permissions(role_id: int, permission_codes: list[str]) -> None:
    now = now_iso()
    with get_connection() as conn:
        conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
        for code in permission_codes:
            conn.execute(
                "INSERT INTO role_permissions(role_id,permission_code,permission_type,created_at) VALUES(?,?,?,?)",
                (role_id, code, "button", now),
            )


def update_user(
    user_id: int,
    display_name: str | None = None,
    department_id: int | None = None,
    role_codes: list[str] | None = None,
    status: str | None = None,
    password: str | None = None,
) -> None:
    now = now_iso()
    with get_connection() as conn:
        if display_name is not None:
            conn.execute("UPDATE users SET display_name=?,updated_at=? WHERE id=?", (display_name, now, user_id))
        if department_id is not None:
            conn.execute("UPDATE users SET department_id=?,updated_at=? WHERE id=?", (department_id, now, user_id))
        if status is not None:
            conn.execute("UPDATE users SET status=?,updated_at=? WHERE id=?", (status, now, user_id))
            if status == "disabled":  # 停用即踢下线（get_current_user 每请求复查兜底）
                conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
        if password:  # 管理员重置密码：置强制改密标记
            conn.execute(
                "UPDATE users SET password_hash=?,must_change_password=1,updated_at=? WHERE id=?",
                (hash_password(password), now, user_id),
            )
        if role_codes is not None:
            conn.execute("DELETE FROM user_roles WHERE user_id=?", (user_id,))
            for code in role_codes:
                role = conn.execute("SELECT id FROM roles WHERE role_code=?", (code,)).fetchone()
                if role:
                    conn.execute(
                        "INSERT INTO user_roles(user_id,role_id,created_at) VALUES(?,?,?)",
                        (user_id, role["id"], now),
                    )


def create_department(name: str, parent_id: int | None = None, leader_id: int | None = None) -> int:
    now = now_iso()
    with get_connection() as conn:
        order = conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 m FROM departments").fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO departments(name,parent_id,leader_id,sort_order,created_at) VALUES(?,?,?,?,?)",
            (name, parent_id, leader_id, order, now),
        )
        return cur.lastrowid


def update_department(dept_id: int, name: str | None = None, parent_id: int | None = None, leader_id: int | None = None) -> None:
    with get_connection() as conn:
        if name is not None:
            conn.execute("UPDATE departments SET name=? WHERE id=?", (name, dept_id))
        if parent_id is not None:
            conn.execute("UPDATE departments SET parent_id=? WHERE id=?", (parent_id, dept_id))
        if leader_id is not None:
            conn.execute("UPDATE departments SET leader_id=? WHERE id=?", (leader_id, dept_id))


def delete_department(dept_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET department_id=NULL WHERE department_id=?", (dept_id,))
        conn.execute("DELETE FROM departments WHERE id=?", (dept_id,))


def create_role(role_name: str, role_code: str, description: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO roles(role_name,role_code,description) VALUES(?,?,?)",
            (role_name, role_code, description),
        )
        return cur.lastrowid


def update_role(role_id: int, role_name: str | None = None, description: str | None = None) -> None:
    with get_connection() as conn:
        if role_name is not None:
            conn.execute("UPDATE roles SET role_name=? WHERE id=?", (role_name, role_id))
        if description is not None:
            conn.execute("UPDATE roles SET description=? WHERE id=?", (description, role_id))


def delete_role(role_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
        conn.execute("DELETE FROM user_roles WHERE role_id=?", (role_id,))
        conn.execute("DELETE FROM roles WHERE id=?", (role_id,))
