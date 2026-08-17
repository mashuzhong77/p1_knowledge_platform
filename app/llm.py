"""DeepSeek 通用调用（OpenAI 兼容）；失败返回空串，由调用方兜底。"""

import logging

from .config import settings

logger = logging.getLogger(__name__)


def chat_completion(prompt: str, json_mode: bool = False, timeout: int = 30) -> str:
    if not settings.deepseek_api_key:
        logger.warning("chat_completion skipped: deepseek_api_key is empty")
        return ""
    try:
        import httpx

        payload = {
            "model": settings.deepseek_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            f"{settings.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        logger.exception("chat_completion failed")
        return ""
