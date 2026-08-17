"""数据看板接口。"""

from fastapi import APIRouter, Depends

from ..auth import require_admin
from ..stats import dashboard_stats, hot_units_with_titles

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics")
def metrics(_: dict = Depends(require_admin)):
    return dashboard_stats()


@router.get("/rankings/questions")
def top_questions(_: dict = Depends(require_admin)):
    return dashboard_stats()["top_questions"]


@router.get("/rankings/units")
def top_units(_: dict = Depends(require_admin)):
    return hot_units_with_titles()


@router.get("/stats/tokens")
def tokens_trend(_: dict = Depends(require_admin)):
    stats = dashboard_stats()
    return {
        "token_consumption": stats["token_consumption"],
        "response_time_trend": stats["response_time_trend"],
    }
