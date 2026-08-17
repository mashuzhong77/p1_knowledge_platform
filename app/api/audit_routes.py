"""审计日志接口。"""

from fastapi import APIRouter, Depends, Query

from .. import audit
from ..auth import require_admin

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
def logs(
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    _: dict = Depends(require_admin),
):
    return audit.list_logs(user_id=user_id, action=action, limit=limit)
