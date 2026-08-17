"""问句改写与知识域识别（框架 R1/R2，蒸馏自 ai_0302 rewritten_query_and_itemnames 模式）。"""

import json
import re

from .llm import chat_completion
from .prompts import load_prompt

HISTORY_LIMIT = 5


def build_history_text(rows: list[dict]) -> str:
    """把历史问答日志拼成可读上下文。rows 按时间倒序传入。"""
    lines = []
    for r in reversed(rows or []):
        q = (r.get("question") or "").strip()
        a = (r.get("answer") or "").strip()
        if q:
            lines.append(f"用户: {q}")
        if a:
            lines.append(f"助手: {a[:120]}")
    return "\n".join(lines) or "（无历史会话）"


def _extract_json(raw: str) -> dict:
    """容错解析：先整体 json.loads，失败则提取第一个 {...}。"""
    raw = (raw or "").strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}


def default_rewrite_call(prompt: str) -> str:
    """DeepSeek JSON 模式改写调用；失败返回空串（由上层兜底）。"""
    return chat_completion(prompt, json_mode=True)


def rewrite_query(
    question: str,
    history_text: str = "",
    llm_call=None,
) -> dict:
    """改写问句 + 识别知识域。llm_call 为 None 或失败时用原问题兜底（离线降级）。"""
    prompt = load_prompt("rewrite_query", history_text=history_text, question=question)
    raw = llm_call(prompt) if llm_call else ""
    data = _extract_json(raw) if raw else {}
    rewritten = (data.get("rewritten_query") or "").strip()
    if not rewritten:
        rewritten = question
    domains = [str(d).strip() for d in (data.get("domains") or []) if str(d).strip()]
    return {"rewritten_query": rewritten[:200], "domains": domains[:3]}
