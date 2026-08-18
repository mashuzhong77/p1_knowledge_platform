"""认证接口：登录 / 当前用户 / 登出 / 修改密码。"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..auth import (
    _bearer_token,
    change_password,
    check_current_password,
    login,
    logout,
    require_session,
    validate_new_password,
)
from ..models import ChangePasswordRequest, LoginRequest
from ..ratelimit import _client_ip, apply_rate_limit, check_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def do_login(body: LoginRequest, request: Request):
    ip = _client_ip(request)
    check_rate_limit(f"login:{ip}", max_requests=10, window_seconds=60)
    check_rate_limit(f"login:user:{body.username}", max_requests=5, window_seconds=60)
    result = login(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return result


@router.get("/me")
def me(user: dict = Depends(require_session)):
    # 含 must_change_password 字段；已登录即可，不强制改密
    return user


@router.post("/logout")
def do_logout(authorization: str | None = Header(default=None)):
    # 不要求有效会话：幂等、永不 401（避免前端 api() 的 401->logout 递归）
    logout(_bearer_token(authorization))
    return {"ok": True}


@router.post("/change-password")
def do_change_password(
    body: ChangePasswordRequest,
    user: dict = Depends(require_session),
    authorization: str | None = Header(default=None),
):
    apply_rate_limit(max_requests=5, window_seconds=60, bucket=f"change_pwd:{user['id']}")
    if not check_current_password(user["id"], body.current_password):
        raise HTTPException(status_code=400, detail="当前密码错误")
    policy_err = validate_new_password(body.new_password, body.current_password)
    if policy_err:
        raise HTTPException(status_code=400, detail=policy_err)
    # 保留当前会话，注销该用户其他会话
    change_password(user["id"], body.new_password, keep_token=_bearer_token(authorization))
    return {"ok": True}
