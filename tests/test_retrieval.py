"""检索增强：RRF 融合、HyDE 降级、动态断崖截断。"""

from app.retrieval import dynamic_topk, hyde_answer, reciprocal_rank_fusion


def test_rrf_fuses_by_rank():
    r1 = [
        {"unit_id": 1, "title": "A"},
        {"unit_id": 2, "title": "B"},
    ]
    r2 = [
        {"unit_id": 2, "title": "B"},
        {"unit_id": 3, "title": "C"},
    ]
    fused = reciprocal_rank_fusion([(r1, 1.0), (r2, 1.0)], top=5)
    by_id = {d["unit_id"]: d["score"] for d in fused}
    # 单元2 在两路都出现，分数应高于只出现一路的单元
    assert by_id[2] > by_id[1]
    assert by_id[2] > by_id[3]
    assert len(fused) == 3


def test_rrf_weighted_and_top_limit():
    r1 = [{"unit_id": 1}, {"unit_id": 2}, {"unit_id": 3}]
    r2 = [{"unit_id": 4}, {"unit_id": 5}]
    fused = reciprocal_rank_fusion([(r1, 2.0), (r2, 1.0)], top=2)
    assert len(fused) == 2
    assert fused[0]["unit_id"] == 1  # 高权重 + 高排名


def test_hyde_offline_returns_empty():
    assert hyde_answer("问题", llm_call=None) == ""


def test_hyde_uses_llm_text():
    def fake_llm(prompt):
        return "假设答案内容"

    assert hyde_answer("问题", llm_call=fake_llm) == "假设答案内容"


def test_dynamic_topk_cuts_at_cliff():
    items = [
        {"unit_id": 1, "score": 0.9},
        {"unit_id": 2, "score": 0.85},
        {"unit_id": 3, "score": 0.2},
        {"unit_id": 4, "score": 0.1},
    ]
    cut = dynamic_topk(items, max_topk=4, gap_abs=0.5)
    assert [d["unit_id"] for d in cut] == [1, 2]


def test_dynamic_topk_keeps_minimum():
    items = [
        {"unit_id": 1, "score": 0.9},
        {"unit_id": 2, "score": 0.1},
    ]
    cut = dynamic_topk(items, min_topk=1, max_topk=2, gap_abs=0.5)
    assert len(cut) == 1
