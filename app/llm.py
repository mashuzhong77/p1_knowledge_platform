"""DeepSeek 通用调用（OpenAI 兼容）；失败返回空串，由调用方兜底。"""

import logging

from .config import settings

logger = logging.getLogger(__name__)


def chat_completion(prompt: str, json_mode: bool = False, timeout: int = 30) -> str:
    if not settings.effective_llm_api_key:
        logger.warning("chat_completion skipped: llm_api_key is empty")
        return ""
    if (settings.llm_base_url and not settings.llm_model) or (
        settings.llm_model and not settings.llm_base_url
    ):
        logger.warning(
            "LLM_BASE_URL/LLM_MODEL 未同时配置：effective_llm_model/base_url 将回退到 deepseek_*，"
            "若目标地址是 vLLM 会请求 404 并静默离线。请 LLM_* 三个都填。"
        )
    try:
        import httpx

        payload = {
            "model": settings.effective_llm_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            f"{settings.effective_llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.effective_llm_api_key}"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        logger.exception("chat_completion failed")
        return ""
