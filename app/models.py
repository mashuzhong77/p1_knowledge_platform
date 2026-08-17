"""Pydantic 请求/响应模型。"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=72)  # bcrypt 的 72 字节上限


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class PermissionItem(BaseModel):
    target_type: str
    target_id: str | int | None = None


class ImportTextRequest(BaseModel):
    title: str
    content: str
    security_level: str = "internal"
    data_domain: str = ""
    scope: list[PermissionItem] | None = None


class UnitUpdateRequest(BaseModel):
    content: str
    summary: str | None = None
    category: str | None = None


class SetPermissionsRequest(BaseModel):
    permissions: list[PermissionItem]


class DeleteUnitsRequest(BaseModel):
    unit_ids: list[int]


class CheckPermissionsRequest(BaseModel):
    user_id: int
    unit_ids: list[int]


class RollbackRequest(BaseModel):
    target_version_id: int


class AskRequest(BaseModel):
    question: str
    session_id: str = ""


class FeedbackRequest(BaseModel):
    session_id: str = ""
    question: str = ""
    answer: str = ""
    rating: str = "up"
    feedback_type: str = "none"
    comment: str = ""


class ReviewRequest(BaseModel):
    action: str  # approve / reject
    edited_answer: str = ""


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    department_id: int | None = None
    role_codes: list[str] = []


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    department_id: int | None = None
    role_codes: list[str] | None = None
    status: str | None = None  # active / disabled
    password: str | None = None  # 可选：重置密码


class DepartmentRequest(BaseModel):
    name: str
    parent_id: int | None = None
    leader_id: int | None = None


class RoleRequest(BaseModel):
    role_name: str
    role_code: str
    description: str = ""


class SetRolePermissionsRequest(BaseModel):
    permission_codes: list[str] = []
