"""问句改写与知识域识别：JSON 解析、离线兜底、历史拼接。"""

from app.rewrite import _extract_json, build_history_text, rewrite_query


def test_rewrite_query_offline_falls_back_to_original():
    result = rewrite_query("它怎么用？", history_text="（无历史会话）", llm_call=None)
    assert result["rewritten_query"] == "它怎么用？"
    assert result["domains"] == []


def test_rewrite_query_parses_llm_json():
    def fake_llm(prompt):
        return '{"rewritten_query": "绿色建筑评价标准包含哪些维度？", "domains": ["绿建"]}'

    result = rewrite_query("绿建标准有哪些维度？", history_text="", llm_call=fake_llm)
    assert result["rewritten_query"] == "绿色建筑评价标准包含哪些维度？"
    assert result["domains"] == ["绿建"]


def test_rewrite_query_invalid_json_falls_back():
    def fake_llm(prompt):
        return "不是 JSON"

    result = rewrite_query("问题", llm_call=fake_llm)
    assert result["rewritten_query"] == "问题"
    assert result["domains"] == []


def test_extract_json_recovers_braced_object():
    assert _extract_json('前缀 {"a": 1} 后缀') == {"a": 1}


def test_build_history_text_orders_oldest_first():
    rows = [
        {"question": "Q2", "answer": "A2"},
        {"question": "Q1", "answer": "A1"},
    ]
    text = build_history_text(rows)
    assert text.index("Q1") < text.index("Q2")
    assert "助手: A1" in text
