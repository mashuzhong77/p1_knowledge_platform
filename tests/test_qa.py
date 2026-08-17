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


def test_ask_gates_on_llm_api_key(db, monkeypatch):
    """新主配置 LLM_*（非 deepseek）也应视为在线：域为空 → out_of_domain 拒答。"""
    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "sk-llm")
    monkeypatch.setattr(settings, "llm_base_url", "http://vllm:8100/v1")
    monkeypatch.setattr(settings, "llm_model", "finetuned-qwen")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": []},
    )
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("今天天气怎么样", user, "s1")
    assert result["status"] == "refused"
    assert result["refuse_reason"] == "out_of_domain"
    assert result["model"] == "finetuned-qwen"


def test_ask_result_carries_model(db, monkeypatch):
    """在线→模型名；离线→空串。"""
    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": []},
    )
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("今天天气怎么样", user, "s1")
    assert result["status"] == "refused"
    assert result["model"] == settings.effective_llm_model

    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(qa, "_offline_has_relevant", lambda q: False)
    result = qa.ask("今天天气怎么样", user, "s1")
    assert result["status"] == "refused"
    assert result["model"] == ""


def test_ask_rerank_wired(db, monkeypatch, tmp_path):
    """配置 RERANK_API_URL 时，qa.rerank 被调用且其输出决定证据。"""
    import app.qa as qa
    from app.config import settings
    from app.database import get_connection
    from app.knowledge.crud import create_unit
    from app.knowledge.fts import FtsStore

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(settings, "rerank_api_url", "http://rr:8102")
    monkeypatch.setattr(settings, "rerank_api_key", "")
    monkeypatch.setattr(settings, "rerank_top", 20)
    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vec")

    with get_connection() as conn:
        uid_a = create_unit(conn, title="文档甲", content="绿色建筑评价指标包括安全耐久维度。", creator_id=1)
        uid_b = create_unit(conn, title="文档乙", content="绿色建筑评价标准包含健康舒适维度。", creator_id=1)
        FtsStore.sync_unit(conn, uid_a)
        FtsStore.sync_unit(conn, uid_b)

    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": ["绿建"]},
    )
    monkeypatch.setattr(qa, "hyde_answer", lambda *a, **k: "")

    called = {}

    def fake_rerank(query, candidates, content_getter, api_url="", api_key="", top=None):
        called["api_url"] = api_url
        called["top"] = top
        # 只保留第二个候选，验证 rerank 输出直接流入证据
        return [candidates[1]]

    monkeypatch.setattr(qa, "rerank", fake_rerank)
    monkeypatch.setattr(qa, "default_llm_call", lambda prompt: "根据[证据1]，绿色建筑评价指标。")

    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    result = qa.ask("绿色建筑有哪些维度？", user, "s1")
    assert called["api_url"] == "http://rr:8102"
    assert called["top"] == 5
    assert result["status"] == "ok"
    assert len(result["evidence"]) == 1
    assert "score" in result["evidence"][0]  # 证据带分数（rerank 分或 RRF 分），前端做置信度
    assert result["evidence"][0]["score"] > 0


def test_chat_stream_emits_model_event_after_deltas(db, client, make_user, monkeypatch):
    """SSE 流在全部 message_delta 之后、progress success 之前发射 model 事件。"""
    import app.api.qa_routes as qa_routes
    from app.database import get_connection

    with get_connection() as conn:
        make_user(conn, username="admin", role_code="admin")

    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    def fake_ask(question, user, session_id="", emit_delta=None):
        if emit_delta is not None:
            emit_delta("测试回答")  # 真流式：逐 token 推 message_delta
        return {
            "status": "ok",
            "answer": "测试回答",
            "evidence": [],
            "blocked": [],
            "model": "finetuned-qwen",
        }

    monkeypatch.setattr(qa_routes, "ask", fake_ask)

    with client.stream(
        "POST",
        "/api/ai/chat/stream",
        headers=headers,
        json={"question": "测试", "session_id": "s1"},
    ) as resp:
        text = "".join(resp.iter_text())

    assert '"event": "model", "model": "finetuned-qwen"' in text
    assert text.index('"event": "message_delta"') < text.index('"event": "model"')
    assert text.index('"event": "model"') < text.index('"event": "progress", "status": "success"')


# ===== 真 token 流式 =====


class _FakeStreamCtx:
    """httpx.stream 上下文模拟：__enter__ 返回可 iter_lines 的响应对象。"""

    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self._resp

    def __exit__(self, *exc):
        return False


def _stream_resp(lines):
    resp = type(
        "R",
        (),
        {"raise_for_status": lambda self: None, "iter_lines": lambda self: iter(lines)},
    )()
    return _FakeStreamCtx(resp)


def test_stream_llm_call_emits_chunks(db, monkeypatch):
    """在线流式：逐 delta 调 on_chunk、返回全文、usage 帧计入 _LAST_USAGE。"""
    import httpx

    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    lines = [
        'data: {"choices":[{"delta":{"content":"你"}}]}\n',
        "",
        'data: {"choices":[{"delta":{"content":"好"}}]}\n',
        "",
        'data: {"choices":[{"delta":{"content":"。"}}],"usage":{"prompt_tokens":10,"completion_tokens":3,"total_tokens":13}}\n',
        "data: [DONE]\n",
    ]
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _stream_resp(lines))

    chunks = []
    full = qa.stream_llm_call("提示", on_chunk=chunks.append)
    assert chunks == ["你", "好", "。"]
    assert full == "你好。"
    assert qa._LAST_USAGE["total_tokens"] == 13


def test_stream_llm_call_fallback_on_error(db, monkeypatch):
    """流式失败（连接错误）→ 降级 default_llm_call 后整串一次 on_chunk。"""
    import httpx

    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")

    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "stream", boom)
    monkeypatch.setattr(qa, "default_llm_call", lambda prompt: "兜底回答")
    chunks = []
    full = qa.stream_llm_call("提示", on_chunk=chunks.append)
    assert full == "兜底回答"
    assert chunks == ["兜底回答"]


def test_ask_stream_emits_deltas(db, monkeypatch, tmp_path):
    """正常生成路径：emit_delta 时走 stream_llm_call，delta 拼接 == 最终答案。"""
    import app.qa as qa
    from app.config import settings
    from app.database import get_connection
    from app.knowledge.crud import create_unit
    from app.knowledge.fts import FtsStore

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vec")
    with get_connection() as conn:
        uid = create_unit(conn, title="绿建", content="绿色建筑评价标准包含安全耐久等维度。", creator_id=1)
        FtsStore.sync_unit(conn, uid)

    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": ["绿建"]},
    )
    monkeypatch.setattr(qa, "hyde_answer", lambda *a, **k: "")

    def fake_stream(prompt, on_chunk):
        for t in ["根据", "证据1", "的答案"]:
            on_chunk(t)
        return "根据证据1的答案"

    monkeypatch.setattr(qa, "stream_llm_call", fake_stream)
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    chunks = []
    result = qa.ask("绿色建筑有哪些维度？", user, "s1", emit_delta=chunks.append)
    assert "".join(chunks) == "根据证据1的答案"
    assert result["answer"] == "根据证据1的答案"


def test_answer_question_refused_stream_emits_text():
    """无证据拒答：emit_delta 收到拒答语。"""
    chunks = []
    result = answer_question("问题", [], [], lambda p: "x", emit_delta=chunks.append)
    assert result["status"] == "refused"
    assert chunks == ["未找到相关资料，无法回答。"]


def test_ask_refused_out_of_domain_stream_emits_text(db, monkeypatch):
    """out_of_domain 拒答：拒答语也经 emit_delta 推给前端。"""
    import app.qa as qa
    from app.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(
        qa,
        "rewrite_query",
        lambda q, h, llm_call=None: {"rewritten_query": q, "domains": []},
    )
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    chunks = []
    result = qa.ask("今天天气怎么样", user, "s1", emit_delta=chunks.append)
    assert result["status"] == "refused"
    assert "不属于本知识库领域" in "".join(chunks)


def test_ask_offline_stream_emits_once(db, monkeypatch, tmp_path):
    """离线（无 key）：default_llm_call 整串一次 emit（仍是单个 message_delta）。"""
    import app.qa as qa
    from app.config import settings
    from app.database import get_connection
    from app.knowledge.crud import create_unit
    from app.knowledge.fts import FtsStore

    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "vector_dir", tmp_path / "vec")
    with get_connection() as conn:
        uid = create_unit(conn, title="绿建", content="绿色建筑评价标准包含安全耐久等维度。", creator_id=1)
        FtsStore.sync_unit(conn, uid)

    monkeypatch.setattr(qa, "_offline_has_relevant", lambda q: True)
    monkeypatch.setattr(qa, "default_llm_call", lambda prompt: "（离线演示模式）根据[证据1]，绿色建筑……")
    user = {"id": 1, "department_id": None, "roles": ["admin"], "role_code": "admin"}
    chunks = []
    result = qa.ask("绿色建筑有哪些维度？", user, "s1", emit_delta=chunks.append)
    assert chunks == [result["answer"]]
    assert len(chunks) == 1
