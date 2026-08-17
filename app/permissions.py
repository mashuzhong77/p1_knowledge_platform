"""数据权限引擎：全局 / 部门 / 角色 / 个人，满足任一即可访问。"""

SCOPE_GLOBAL = "global"
SCOPE_DEPARTMENT = "department"
SCOPE_ROLE = "role"
SCOPE_PERSONAL = "personal"


def security_allows(unit: dict, user: dict) -> bool:
    """密级校验（企业级亮点 5）：open/internal 登录即可；confidential 需权限码或 admin。"""
    level = (unit.get("security_level") or "internal").strip().lower()
    if level == "confidential":
        return (
            "admin" in (user.get("roles") or [])
            or "knowledge:confidential" in (user.get("permissions") or [])
        )
    return True  # open / internal / 未知级别：配合数据权限即可


def can_access(unit: dict, user: dict) -> bool:
    """单作用域判断（用于单元测试与简单场景）。"""
    scope = unit.get("scope_type")
    if scope == SCOPE_GLOBAL:
        return True
    if scope == SCOPE_DEPARTMENT:
        return unit.get("department_id") == user.get("department_id")
    if scope == SCOPE_ROLE:
        return unit.get("role_code") == user.get("role_code")
    if scope == SCOPE_PERSONAL:
        return unit.get("owner_id") == user.get("id")
    return False


def filter_accessible(units: list[dict], user: dict) -> list[dict]:
    return [u for u in units if can_access(u, user)]


def unit_allows(unit_row: dict, user: dict) -> bool:
    """基于 unit_permissions 行集合判断（unit_row 含 perms 字段）。"""
    if not security_allows(unit_row, user):
        return False
    perms = unit_row.get("perms") or []
    if not perms:
        return unit_row.get("creator_id") == user.get("id")
    for p in perms:
        target_type = p.get("target_type")
        target_id = str(p.get("target_id") or "")
        if target_type == SCOPE_GLOBAL:
            return True
        if target_type == SCOPE_DEPARTMENT:
            if str(user.get("department_id") or "") == target_id:
                return True
        elif target_type == SCOPE_ROLE:
            if target_id in (user.get("roles") or []):
                return True
        elif target_type == "user":
            if str(user.get("id") or "") == target_id:
                return True
    return False
