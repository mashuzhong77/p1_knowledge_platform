"""MMR 去冗余：单候选原样 / 同源去冗余 / λ 权衡 / 缺内容候选 / top 截断。"""

from app.retrieval import mmr_diverse

CANDIDATES = [
    {"unit_id": 1, "score": 0.9, "title": "A"},
    {"unit_id": 2, "score": 0.85, "title": "B"},
    {"unit_id": 3, "score": 0.5, "title": "C"},
]

CONTENTS = {
    1: "甲甲甲甲乙乙乙乙丙丙丙丙丁丁丁丁",  # 与 2 同源（内容几乎相同）
    2: "甲甲甲甲乙乙乙乙丙丙丙丙丁丁丁丁",
    3: "完全不同的另一份文档内容完全不同",
}


def _getter(unit_ids):
    return {i: CONTENTS[i] for i in unit_ids if i in CONTENTS}


def _ids(cands):
    return [c["unit_id"] for c in cands]


def test_single_candidate_returned_as_is():
    single = CANDIDATES[:1]
    out = mmr_diverse(single, content_getter=_getter)
    assert out is single


def test_deduplicates_similar_documents():
    # λ=0.7：同源 B 与最高分 A 相似度≈1 被压制，第二选落到不同源的 C
    out = mmr_diverse(CANDIDATES, content_getter=_getter, lambda_=0.7, top=2)
    assert _ids(out) == [1, 3]


def test_lambda_one_pure_relevance():
    # λ=1：只看相关分，B(0.85) 胜 C(0.5)
    out = mmr_diverse(CANDIDATES, content_getter=_getter, lambda_=1.0, top=2)
    assert _ids(out) == [1, 2]


def test_lambda_zero_pure_diversity():
    # λ=0：只看多样性，与已选最不相似者胜出
    out = mmr_diverse(CANDIDATES, content_getter=_getter, lambda_=0.0, top=2)
    assert _ids(out) == [1, 3]


def test_top_truncates_output():
    out = mmr_diverse(CANDIDATES, content_getter=_getter, lambda_=0.7, top=1)
    assert _ids(out) == [1]


def test_missing_content_candidate_excluded():
    def getter(unit_ids):
        return {1: CONTENTS[1], 2: CONTENTS[2]}  # 3 无内容 → 不进候选池

    out = mmr_diverse(CANDIDATES, content_getter=getter, lambda_=0.7, top=2)
    assert _ids(out) == [1, 2]
    assert 3 not in _ids(out)


def test_pool_under_two_falls_back_to_input():
    def getter(unit_ids):
        return {1: CONTENTS[1]}  # 只有 1 有内容 → pool<2 → 原样返回

    out = mmr_diverse(CANDIDATES, content_getter=getter, lambda_=0.7)
    assert out is CANDIDATES
