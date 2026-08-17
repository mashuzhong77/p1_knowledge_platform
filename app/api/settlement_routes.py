"""知识沉淀接口：FAQ / 反馈 / 缺口。"""

from fastapi import APIRouter, Depends

from .. import audit
from ..auth import require_admin, require_user
from ..models import FeedbackRequest, ReviewRequest
from ..settlement import (
    list_gaps,
    list_recommendations,
    mine_faq,
    publish_faq,
    record_feedback,
    reject_faq,
)

router = APIRouter(prefix="/api/settlement", tags=["settlement"])


@router.get("/faqs/recommendations")
def recommendations(_: dict = Depends(require_admin)):
    mine_faq(min_count=2)
    return list_recommendations()


@router.post("/faqs/{faq_id}/review")
def review(faq_id: int, body: ReviewRequest, user: dict = Depends(require_admin)):
    if body.action == "approve":
        publish_faq(faq_id, body.edited_answer, user["id"])
    elif body.action == "reject":
        reject_faq(faq_id, user["id"])
    else:
        return {"ok": False, "error": "action 必须为 approve/reject"}
    audit.log_action(user["id"], "review_faq", "faq", faq_id, {"action": body.action})
    return {"ok": True}


@router.get("/knowledge-gaps")
def gaps(_: dict = Depends(require_admin)):
    return list_gaps()


@router.post("/feedback")
def feedback(body: FeedbackRequest, user: dict = Depends(require_user)):
    record_feedback(body.model_dump(), user["id"])
    return {"ok": True}
