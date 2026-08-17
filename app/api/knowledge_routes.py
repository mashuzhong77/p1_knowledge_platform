"""知识库接口：导入 / CRUD / 权限 / 版本。"""

import asyncio
import json
import uuid
from pathlib import Path as _Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from .. import audit
from ..auth import has_permission, require_user, roles_of
from ..config import settings
from ..database import db, get_connection
from ..knowledge import crud, importer
from ..knowledge.vectorstore import get_vectorstore
from ..tasks import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PROCESSING,
    add_done_task,
    create_task,
    get_task,
    set_task_error,
    set_task_result,
    update_task_status,
)
from ..models import (
    CheckPermissionsRequest,
    DeleteUnitsRequest,
    ImportTextRequest,
    RollbackRequest,
    SetPermissionsRequest,
    UnitUpdateRequest,
)
from ..permissions import unit_allows

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_UPLOAD_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


def sanitize_filename(original: str | None) -> str:
    """取纯文件名，剥离任意路径分隔符；非法时回退 uuid。"""
    if not original:
        return f"upload_{uuid.uuid4().hex}"
    name = _Path(original.replace("\\", "/")).name.strip()  # 跨平台处理反斜杠路径穿越
    if not name or name in {".", ".."}:
        return f"upload_{uuid.uuid4().hex}"
    return name


def read_limited(stream, max_bytes: int) -> bytes:
    """分块读取并计数，超限抛 413。"""
    chunks, total = [], 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="文件超过大小限制")
        chunks.append(chunk)
    return b"".join(chunks)


def _load(conn, unit_id: int) -> dict:
    u = crud.get_unit(conn, unit_id)
    if u is None:
        raise HTTPException(status_code=404, detail="知识单元不存在")
    return u


def _check_access(u: dict, user: dict) -> None:
    if not unit_allows(u, user):
        raise HTTPException(status_code=403, detail="无权限访问该知识单元")


@router.post("/import-text")
def import_text_api(body: ImportTextRequest, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:import"):
        raise HTTPException(status_code=403, detail="缺少导入权限")
    if len(body.content) > settings.max_text_chars:
        raise HTTPException(status_code=413, detail="导入文本超过长度限制")
    scope = [
        {"target_type": p.target_type, "target_id": p.target_id} for p in (body.scope or [])
    ]
    try:
        result = importer.import_text(
            title=body.title,
            content=body.content,
            creator_id=user["id"],
            security_level=body.security_level,
            data_domain=body.data_domain,
            scope=scope or None,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit.log_action(user["id"], "import", "knowledge_unit", ",".join(map(str, result.get("unit_ids", []))))
    return result


def run_import_task(
    task_id: str,
    path,
    creator_id: int,
    security_level: str,
    data_domain: str,
    scope_list: list[dict],
    source_name: str | None = None,
) -> None:
    """后台导入：状态 processing → completed/failed（R7 任务进度）。"""
    update_task_status(task_id, STATUS_PROCESSING)
    try:
        result = importer.import_file(
            path,
            creator_id=creator_id,
            security_level=security_level,
            data_domain=data_domain,
            scope=scope_list or None,
            source_name=source_name,
        )
        add_done_task(task_id, "import")
        update_task_status(task_id, STATUS_COMPLETED)
        set_task_result(task_id, result)
    except Exception as e:  # noqa: BLE001
        update_task_status(task_id, STATUS_FAILED)
        set_task_error(task_id, str(e))


@router.post("/import")
async def import_file_api(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    security_level: str = Form("internal"),
    data_domain: str = Form(""),
    scope: str = Form(""),
    user: dict = Depends(require_user),
):
    if not has_permission(user, "knowledge:import"):
        raise HTTPException(status_code=403, detail="缺少导入权限")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    scope_list: list[dict] = []
    if scope:
        try:
            scope_list = [
                {"target_type": p["target_type"], "target_id": p.get("target_id")}
                for p in json.loads(scope)
            ]
        except Exception:  # noqa: BLE001
            scope_list = []
    # 先全部校验，再统一处理（无部分副作用）
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    validated: list[tuple[str, bytes]] = []
    for file in files:
        safe = sanitize_filename(file.filename)
        ext = _Path(safe).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext or '无扩展名'}")
        data = await asyncio.to_thread(read_limited, file.file, max_bytes)  # 分块计数，超限 413
        validated.append((safe, data))
    task_ids: list[str] = []
    for safe, data in validated:
        disk_name = f"{uuid.uuid4().hex}_{safe}"  # 唯一落盘名，杜绝同请求同名互相覆盖
        path = settings.upload_dir / disk_name
        path.write_bytes(data)
        task_id = str(uuid.uuid4())
        create_task(task_id)
        background.add_task(
            run_import_task,
            task_id,
            path,
            user["id"],
            security_level,
            data_domain,
            scope_list,
            source_name=safe,
        )
        audit.log_action(user["id"], "import_file", "file", safe, {"task_id": task_id})
        task_ids.append(task_id)
    return {"code": 200, "task_ids": task_ids, "message": f"已提交 {len(task_ids)} 个导入任务"}


@router.get("/import/status/{task_id}")
def import_status_api(task_id: str, user: dict = Depends(require_user)):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return {"task_id": task_id, **task}


@router.get("/units")
def list_units_api(
    category: str | None = None,
    status: str | None = None,
    user: dict = Depends(require_user),
):
    with get_connection() as conn:
        units = crud.list_units(conn, user, category=category, status=status)
        # 有权限配置能力的用户可见数据权限摘要，用于列表展示与配置回填
        if has_permission(user, "knowledge:permission"):
            for u in units:
                u["perms"] = crud.get_unit_permissions(conn, u["id"])
    return units


@router.get("/units/{unit_id}")
def get_unit_api(unit_id: int, user: dict = Depends(require_user)):
    with get_connection() as conn:
        u = _load(conn, unit_id)
        _check_access(u, user)
        # 有权限配置能力的用户可读取已配置的数据权限（用于配置界面回填）
        if not has_permission(user, "knowledge:permission"):
            u.pop("perms", None)
        return u


@router.put("/units/{unit_id}")
def update_unit_api(unit_id: int, body: UnitUpdateRequest, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:edit"):
        raise HTTPException(status_code=403, detail="缺少编辑权限")
    with db() as conn:
        u = _load(conn, unit_id)
        _check_access(u, user)
        new_id = crud.update_unit_content(
            conn,
            unit_id,
            body.content,
            user_id=user["id"],
            summary=body.summary,
            category=body.category,
        )
        audit.log_action(user["id"], "update_unit", "knowledge_unit", unit_id, {"new_id": new_id}, conn=conn)
    return {"id": new_id}


@router.post("/units/{unit_id}/permissions")
def set_permissions_api(unit_id: int, body: SetPermissionsRequest, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:permission"):
        raise HTTPException(status_code=403, detail="缺少权限配置权限")
    with db() as conn:
        _load(conn, unit_id)
        perms = [{"target_type": p.target_type, "target_id": p.target_id} for p in body.permissions]
        crud.set_unit_permissions(conn, unit_id, perms)
        audit.log_action(user["id"], "set_permissions", "knowledge_unit", unit_id, {"permissions": perms}, conn=conn)
    return {"ok": True}


@router.delete("/units")
def delete_units_api(body: DeleteUnitsRequest, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:delete"):
        raise HTTPException(status_code=403, detail="缺少删除权限")
    with db() as conn:
        deleted = crud.delete_units(conn, body.unit_ids)
    try:
        get_vectorstore().delete(deleted)
    except Exception:  # noqa: BLE001
        pass
    audit.log_action(user["id"], "delete_units", "knowledge_unit", ",".join(map(str, body.unit_ids)), {"deleted": deleted})
    return {"deleted": deleted}


@router.post("/check-permissions")
def check_permissions_api(body: CheckPermissionsRequest, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:permission"):
        raise HTTPException(status_code=403, detail="缺少权限")
    authorized, unauthorized = [], []
    with get_connection() as conn:
        target_user = conn.execute("SELECT * FROM users WHERE id=?", (body.user_id,)).fetchone()
        target = {"id": body.user_id, "department_id": None, "roles": []}
        if target_user:
            target["department_id"] = target_user["department_id"]
            target["roles"] = roles_of(conn, body.user_id)
        for uid in body.unit_ids:
            u = crud.get_unit(conn, uid)
            if u and unit_allows(u, target):
                authorized.append(uid)
            else:
                unauthorized.append(uid)
    return {"authorized_unit_ids": authorized, "unauthorized_unit_ids": unauthorized}


@router.post("/units/{unit_id}/publish")
def publish_api(unit_id: int, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:edit"):
        raise HTTPException(status_code=403, detail="缺少编辑权限")
    with db() as conn:
        _load(conn, unit_id)
        crud.publish_unit(conn, unit_id, reviewer_id=user["id"])
        audit.log_action(user["id"], "publish", "knowledge_unit", unit_id, conn=conn)
    return {"ok": True}


@router.post("/units/{unit_id}/archive")
def archive_api(unit_id: int, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:edit"):
        raise HTTPException(status_code=403, detail="缺少编辑权限")
    with db() as conn:
        _load(conn, unit_id)
        crud.archive_unit(conn, unit_id)
        audit.log_action(user["id"], "archive", "knowledge_unit", unit_id, conn=conn)
    return {"ok": True}


@router.post("/units/{unit_id}/rollback")
def rollback_api(unit_id: int, body: RollbackRequest, user: dict = Depends(require_user)):
    if not has_permission(user, "knowledge:edit"):
        raise HTTPException(status_code=403, detail="缺少编辑权限")
    with db() as conn:
        _load(conn, unit_id)
        new_id = crud.rollback_unit(conn, unit_id, body.target_version_id, user_id=user["id"])
        audit.log_action(user["id"], "rollback", "knowledge_unit", unit_id, {"target_version_id": body.target_version_id, "new_id": new_id}, conn=conn)
    return {"id": new_id}


@router.get("/units/{unit_id}/versions")
def versions_api(unit_id: int, user: dict = Depends(require_user)):
    with get_connection() as conn:
        _load(conn, unit_id)
        return crud.list_versions(conn, unit_id)
