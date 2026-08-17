"""提示词外置：模板文件存在、可渲染、缺失时回退内嵌。"""

from app.prompts import load_prompt
from app.qa import PROMPT_TEMPLATE, build_prompt


def test_c_rag_answer_prompt_file_renders_variables():
    prompt = load_prompt(
        "c_rag_answer",
        question="什么是双碳？",
        context="[证据1] 双碳目标指 2030 年碳达峰。",
        blocked_hint="",
    )
    assert "什么是双碳？" in prompt
    assert "[证据1]" in prompt
    assert "仅依据" in prompt


def test_build_prompt_keeps_contract_and_blocked_hint():
    evidence = [{"id": 1, "content": "内容", "source": "资料"}]
    prompt = build_prompt("问题", evidence, ["涉密A"])
    assert "[证据1]" in prompt
    assert "另有 1 条相关片段因无权限访问无法展示" in prompt


def test_qa_template_loaded_from_external_file():
    assert "待处理数据" in PROMPT_TEMPLATE
