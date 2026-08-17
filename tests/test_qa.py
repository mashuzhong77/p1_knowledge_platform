"""RAG 问答契约：无证据拒答、证据编号可校验、无权限项提示。"""

from app.qa import answer_question, build_prompt, parse_evidence_numbers


EVIDENCE = [
    {"id": 1, "content": "绿色建筑评价指标包括安全耐久、健康舒适等维度。", "source": "示例资料"},
    {"id": 2, "content": "双碳目标指 2030 年碳达峰、2060 年碳中和。", "source": "示例资料"},
]


def test_no_evidence_refuses_to_answer():
    result = answer_question("什么是绿建？", evidence=[], blocked=[], llm_call=lambda p: "随便回答")
    assert result["status"] == "refused"
    assert "未找到相关资料" in result["answer"]
    assert result["evidence_ids"] == []


def test_answer_contains_only_real_evidence_numbers():
    def fake_llm(prompt):
        assert "[证据1]" in prompt and "[证据2]" in prompt
        return "根据[证据1]和[证据2]，绿建与双碳分别指……"

    result = answer_question("解释绿建与双碳", evidence=EVIDENCE, blocked=[], llm_call=fake_llm)
    assert result["status"] == "ok"
    assert result["evidence_ids"] == [1, 2]
    assert result["answer"].startswith("根据[证据1]")


def test_blocked_units_are_reported_as_partial():
    def fake_llm(prompt):
        assert "无权限访问" in prompt
        return "根据[证据1]，……"

    result = answer_question("查某规范", evidence=EVIDENCE, blocked=["涉密规范A"], llm_call=fake_llm)
    assert result["status"] == "partial"
    assert result["blocked"] == ["涉密规范A"]


def test_prompt_contains_contract_clauses():
    prompt = build_prompt("什么是双碳？", EVIDENCE, blocked=[])
    assert "仅依据" in prompt
    assert "待处理数据" in prompt
    assert "[证据1]" in prompt


def test_parse_evidence_numbers_extracts_all_numbers():
    assert parse_evidence_numbers("见[证据2]和[证据5]，忽略[证据99]") == [2, 5, 99]


def test_ask_uses_published_faq_cache(db):
    from app.database import db, get_connection
    from app.qa import ask
    from app.settlement import publish_faq

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO faqs(question,answer,status,hit_count,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("什么是绿色建筑？", "FAQ 缓存答案", "pending_review", 0, "2026-08-17", "2026-08-17"),
        )
        faq_id = cur.lastrowid
    publish_faq(faq_id, "FAQ 缓存答案", 1)

    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = ask("什么是绿色建筑？", user, session_id="s1")
    assert result["status"] == "faq_cache"
    assert result["answer"] == "FAQ 缓存答案"
    assert result["cached"] is True

    with get_connection() as conn:
        row = conn.execute("SELECT hit_count FROM faqs WHERE question=?", ("什么是绿色建筑？",)).fetchone()
        assert row["hit_count"] >= 1


def test_ask_records_real_tokens(db, monkeypatch, tmp_path):
    import app.qa as qa
    from app.config import settings
    from app.database import get_connection
    from app.knowledge.crud import create_unit
    from app.knowledge.fts import FtsStore

    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vec")
    with get_connection() as conn:
        uid = create_unit(conn, title="绿建", content="绿色建筑评价标准包含安全耐久等维度。", creator_id=1)
        FtsStore.sync_unit(conn, uid)

    def fake_llm(prompt):
        qa._LAST_USAGE.update(
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        )
        return "根据[证据1]，绿色建筑评价标准包含安全耐久等维度。"

    monkeypatch.setattr(qa, "default_llm_call", fake_llm)
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("绿色建筑有哪些维度？", user, "s1")
    assert result["tokens"]["total_tokens"] == 15

    with get_connection() as conn:
        row = conn.execute(
            "SELECT prompt_tokens, completion_tokens, total_tokens FROM qa_access_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["prompt_tokens"] == 10
        assert row["completion_tokens"] == 5
        assert row["total_tokens"] == 15


def test_ask_refuses_out_of_domain_when_online(db, monkeypatch):
    import app.qa as qa
    from app.config import settings
    from app.database import get_connection

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": []},
    )
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("今天天气怎么样", user, "s1")
    assert result["status"] == "refused"
    assert result["refuse_reason"] == "out_of_domain"
    assert "不属于本知识库领域" in result["answer"]

    with get_connection() as conn:
        row = conn.execute(
            "SELECT question, answer FROM qa_access_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["question"] == "今天天气怎么样"


def test_ask_refuses_low_score_when_offline(db, monkeypatch):
    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(qa, "_offline_has_relevant", lambda q: False)
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("今天天气怎么样", user, "s1")
    assert result["status"] == "refused"
    assert result["refuse_reason"] == "low_score"
    assert "未找到相关资料" in result["answer"]


def test_ask_does_not_refuse_when_domain_recognized(db, monkeypatch):
    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": ["绿建"]},
    )
    # 域识别非空 → 不触发 out_of_domain / low_score 门控（无证据的 refused 是原有行为）
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("什么是绿色建筑", user, "s1")
    assert result.get("refuse_reason") is None
