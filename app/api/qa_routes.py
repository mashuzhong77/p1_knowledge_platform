"""AI 问答接口：SSE 流式回答。"""

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..auth import require_user
from ..models import AskRequest
from ..qa import ask

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(body: AskRequest, user: dict = Depends(require_user)):
    async def gen():
        yield _sse({"event": "message_start", "session_id": body.session_id})
        yield _sse({"event": "progress", "status": "processing", "step": "检索与生成"})
        result = await asyncio.to_thread(ask, body.question, user, body.session_id or "")
        answer = result["answer"]
        step = 12
        for i in range(0, len(answer), step):
            yield _sse({"event": "message_delta", "delta": answer[i : i + step]})
            await asyncio.sleep(0.01)
        yield _sse({"event": "evidence", "evidence": result.get("evidence", [])})
        yield _sse({"event": "blocked", "blocked": result.get("blocked", [])})
        yield _sse({"event": "progress", "status": "success", "step": "完成"})
        yield _sse({"event": "task_status", "task_status": "success"})
        yield _sse({"event": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream")
