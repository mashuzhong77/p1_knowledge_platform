"""组织架构接口：部门 / 用户 / 角色 / 权限码。"""

from fastapi import APIRouter, Depends, HTTPException

from .. import audit
from ..auth import has_permission, require_admin, require_user
from ..models import (
    CreateUserRequest,
    DepartmentRequest,
    RoleRequest,
    SetRolePermissionsRequest,
    UpdateUserRequest,
)
from ..org import (
    create_department,
    create_role,
    create_user,
    delete_department,
    delete_role,
    list_departments,
    list_roles,
    list_users,
    set_role_permissions,
    update_department,
    update_role,
    update_user,
)

router = APIRouter(prefix="/api/org", tags=["org"])

# 操作权限码目录（前端渲染权限树用）
PERMISSION_CATALOG = [
    {"code": "knowledge:view", "label": "知识查看"},
    {"code": "knowledge:edit", "label": "知识编辑"},
    {"code": "knowledge:import", "label": "知识导入"},
    {"code": "knowledge:delete", "label": "知识删除"},
    {"code": "knowledge:permission", "label": "权限配置"},
    {"code": "knowledge:confidential", "label": "机密访问"},
    {"code": "ai:chat", "label": "AI 问答访问"},
    {"code": "dashboard:view", "label": "看板查看"},
    {"code": "faq:review", "label": "FAQ 审核"},
    {"code": "audit:view", "label": "审计查看"},
]


@router.get("/departments")
def get_departments(_: dict = Depends(require_admin)):
    return list_departments()


@router.post("/departments")
def add_department(body: DepartmentRequest, user: dict = Depends(require_admin)):
    dept_id = create_department(body.name, body.parent_id, body.leader_id)
    audit.log_action(user["id"], "create_department", "department", dept_id, {"name": body.name})
    return {"id": dept_id}


@router.put("/departments/{dept_id}")
def edit_department(dept_id: int, body: DepartmentRequest, user: dict = Depends(require_admin)):
    if dept_id == body.parent_id:
        raise HTTPException(status_code=400, detail="部门不能作为自己的上级")
    update_department(dept_id, body.name, body.parent_id, body.leader_id)
    audit.log_action(user["id"], "update_department", "department", dept_id, {"name": body.name})
    return {"ok": True}


@router.delete("/departments/{dept_id}")
def remove_department(dept_id: int, user: dict = Depends(require_admin)):
    delete_department(dept_id)
    audit.log_action(user["id"], "delete_department", "department", dept_id)
    return {"ok": True}


@router.get("/users")
def get_users(_: dict = Depends(require_admin)):
    return list_users()


@router.post("/users")
def add_user(body: CreateUserRequest, user: dict = Depends(require_admin)):
    user_id = create_user(
        username=body.username,
        password=body.password,
        display_name=body.display_name,
        department_id=body.department_id,
        role_codes=body.role_codes,
    )
    audit.log_action(user["id"], "create_user", "user", user_id, {"username": body.username})
    return {"id": user_id}


@router.put("/users/{user_id}")
def edit_user(user_id: int, body: UpdateUserRequest, user: dict = Depends(require_admin)):
    if user_id == user["id"] and body.status == "disabled":
        raise HTTPException(status_code=400, detail="不能停用当前登录账号")
    update_user(
        user_id,
        display_name=body.display_name,
        department_id=body.department_id,
        role_codes=body.role_codes,
        status=body.status,
        password=body.password,
    )
    audit.log_action(user["id"], "update_user", "user", user_id, {"status": body.status, "reset_pwd": bool(body.password)})
    return {"ok": True}


@router.get("/roles")
def get_roles(_: dict = Depends(require_admin)):
    return list_roles()


@router.post("/roles")
def add_role(body: RoleRequest, user: dict = Depends(require_admin)):
    role_id = create_role(body.role_name, body.role_code, body.description)
    audit.log_action(user["id"], "create_role", "role", role_id, {"role_code": body.role_code})
    return {"id": role_id}


@router.put("/roles/{role_id}")
def edit_role(role_id: int, body: RoleRequest, user: dict = Depends(require_admin)):
    update_role(role_id, body.role_name, body.description)
    audit.log_action(user["id"], "update_role", "role", role_id, {"role_name": body.role_name})
    return {"ok": True}


@router.delete("/roles/{role_id}")
def remove_role(role_id: int, user: dict = Depends(require_admin)):
    delete_role(role_id)
    audit.log_action(user["id"], "delete_role", "role", role_id)
    return {"ok": True}


@router.post("/roles/{role_id}/permissions")
def assign_permissions(role_id: int, body: SetRolePermissionsRequest, user: dict = Depends(require_admin)):
    set_role_permissions(role_id, body.permission_codes)
    audit.log_action(
        user["id"],
        "set_role_permissions",
        "role",
        role_id,
        {"permission_codes": body.permission_codes},
    )
    return {"ok": True}


@router.get("/permissions")
def permission_catalog(_: dict = Depends(require_admin)):
    return PERMISSION_CATALOG


@router.get("/permission-options")
def permission_options(user: dict = Depends(require_user)):
    """数据权限配置弹窗的候选数据：部门 / 角色 / 用户（知识管理员可用）。"""
    if not has_permission(user, "knowledge:permission"):
        raise HTTPException(status_code=403, detail="缺少权限配置权限")
    return {
        "departments": [{"id": d["id"], "name": d["name"]} for d in list_departments()],
        "roles": [
            {"id": r["id"], "role_name": r["role_name"], "role_code": r["role_code"]}
            for r in list_roles()
        ],
        "users": [
            {"id": u["id"], "username": u["username"], "display_name": u.get("display_name") or ""}
            for u in list_users()
        ],
    }
