"""提示词外置：从 app/resources/prompts/ 加载模板并渲染（蒸馏自 ai_0302 知识库 load_prompt 模式）。"""

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "resources" / "prompts"


def load_prompt(name: str, **kwargs) -> str:
    """加载 {name}.prompt 并渲染占位符；无参数时返回原文。"""
    path = PROMPT_DIR / f"{name}.prompt"
    raw = path.read_text(encoding="utf-8")
    return raw.format(**kwargs) if kwargs else raw
