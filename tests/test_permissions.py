"""数据权限判断：全局 / 部门 / 角色 / 个人 + 密级（open/internal/confidential）。"""

from app.permissions import can_access, filter_accessible, security_allows, unit_allows


def test_global_scope_allows_any_user():
    unit = {"scope_type": "global", "department_id": None, "role_code": None, "owner_id": None}
    user = {"id": 1, "department_id": 2, "role_code": "viewer"}
    assert can_access(unit, user) is True


def test_department_scope_allows_only_same_department():
    unit = {"scope_type": "department", "department_id": 3, "role_code": None, "owner_id": None}
    same_dept = {"id": 1, "department_id": 3, "role_code": "viewer"}
    other_dept = {"id": 2, "department_id": 4, "role_code": "viewer"}
    assert can_access(unit, same_dept) is True
    assert can_access(unit, other_dept) is False


def test_role_scope_allows_matching_role():
    unit = {"scope_type": "role", "department_id": None, "role_code": "admin", "owner_id": None}
    admin = {"id": 1, "department_id": 1, "role_code": "admin"}
    viewer = {"id": 2, "department_id": 1, "role_code": "viewer"}
    assert can_access(unit, admin) is True
    assert can_access(unit, viewer) is False


def test_personal_scope_allows_owner_only():
    unit = {"scope_type": "personal", "department_id": None, "role_code": None, "owner_id": 7}
    owner = {"id": 7, "department_id": 1, "role_code": "viewer"}
    stranger = {"id": 8, "department_id": 1, "role_code": "viewer"}
    assert can_access(unit, owner) is True
    assert can_access(unit, stranger) is False


def test_filter_accessible_returns_only_accessible_units():
    units = [
        {"id": 1, "scope_type": "global", "department_id": None, "role_code": None, "owner_id": None},
        {"id": 2, "scope_type": "department", "department_id": 3, "role_code": None, "owner_id": None},
        {"id": 3, "scope_type": "personal", "department_id": None, "role_code": None, "owner_id": 8},
    ]
    user = {"id": 9, "department_id": 3, "role_code": "viewer"}
    result = filter_accessible(units, user)
    assert [u["id"] for u in result] == [1, 2]


def test_security_open_and_internal_allows_logged_user():
    for level in ("open", "internal"):
        unit = {"security_level": level}
        user = {"id": 1, "roles": ["viewer"], "permissions": []}
        assert security_allows(unit, user) is True


def test_security_confidential_denies_regular_user():
    unit = {"security_level": "confidential"}
    viewer = {"id": 1, "roles": ["viewer"], "permissions": ["knowledge:view"]}
    assert security_allows(unit, viewer) is False


def test_security_confidential_allows_admin_or_permission():
    unit = {"security_level": "confidential"}
    admin = {"id": 1, "roles": ["admin"], "permissions": []}
    permitted = {"id": 2, "roles": ["editor"], "permissions": ["knowledge:confidential"]}
    assert security_allows(unit, admin) is True
    assert security_allows(unit, permitted) is True


def test_security_unknown_level_is_lenient():
    unit = {"security_level": "top-secret-custom"}
    user = {"id": 1, "roles": ["viewer"], "permissions": []}
    assert security_allows(unit, user) is True


def test_unit_allows_applies_security_level():
    confidential = {
        "security_level": "confidential",
        "perms": [{"target_type": "user", "target_id": "1"}],
        "creator_id": 1,
    }
    viewer = {"id": 1, "department_id": None, "roles": ["viewer"], "permissions": ["knowledge:view"]}
    admin = {"id": 1, "department_id": None, "roles": ["admin"], "permissions": []}
    assert unit_allows(confidential, viewer) is False
    assert unit_allows(confidential, admin) is True
