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
        # 真流式：ask() 在线程池跑（内部检索+LLM），LLM token 经 emit 塞队列，本协程逐块 yield
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        holder: dict = {}

        def emit(delta: str):
            queue.put_nowait(delta)  # asyncio.Queue.put_nowait 线程安全

        def run():
            holder["result"] = ask(body.question, user, body.session_id or "", emit_delta=emit)
            queue.put_nowait(None)  # 结束哨兵

        loop.run_in_executor(None, run)
        while True:
            delta = await queue.get()
            if delta is None:
                break
            yield _sse({"event": "message_delta", "delta": delta})

        result = holder["result"]
        yield _sse({"event": "evidence", "evidence": result.get("evidence", [])})
        yield _sse({"event": "blocked", "blocked": result.get("blocked", [])})
        yield _sse({"event": "model", "model": result.get("model", "")})
        yield _sse({"event": "progress", "status": "success", "step": "完成"})
        yield _sse({"event": "task_status", "task_status": "success"})
        yield _sse({"event": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream")
