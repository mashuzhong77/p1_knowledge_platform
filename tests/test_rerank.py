"""远程 BGE-reranker：sentence_pairs 格式、分数覆盖排序、降级回退。"""

import httpx

from app.retrieval import rerank

CANDIDATES = [
    {"unit_id": 1, "score": 0.9, "title": "A"},
    {"unit_id": 2, "score": 0.8, "title": "B"},
    {"unit_id": 3, "score": 0.7, "title": "C"},
]

CONTENTS = {1: "绿建文档内容 A", 2: "绿建文档内容 B", 3: "绿建文档内容 C"}


def _getter(unit_ids):
    return {i: CONTENTS[i] for i in unit_ids if i in CONTENTS}


class _FakeResp:
    def __init__(self, scores):
        self._scores = scores

    def raise_for_status(self):
        pass

    def json(self):
        return {"scores": self._scores}


def test_rerank_sends_sentence_pairs_and_orders_by_score(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp([0.1, 0.9, 0.5])

    monkeypatch.setattr(httpx, "post", fake_post)
    out = rerank("查询", CANDIDATES, content_getter=_getter, api_url="http://rr:8102", top=5)
    assert captured["url"] == "http://rr:8102/v1/rerank"
    assert captured["json"] == {
        "sentence_pairs": [["查询", "绿建文档内容 A"], ["查询", "绿建文档内容 B"], ["查询", "绿建文档内容 C"]]
    }
    assert [d["unit_id"] for d in out] == [2, 3, 1]
    assert out[0]["score"] == 0.9
    assert out[0]["rerank_score"] == 0.9
    assert out[0]["fused_score"] == 0.8


def test_rerank_top_truncates(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _FakeResp([0.1, 0.2, 0.3])

    monkeypatch.setattr(httpx, "post", fake_post)
    out = rerank("查询", CANDIDATES, content_getter=_getter, api_url="http://rr:8102", top=2)
    assert len(out) == 2


def test_rerank_empty_api_url_returns_as_is():
    out = rerank("查询", CANDIDATES, content_getter=_getter, api_url="")
    assert out is CANDIDATES


def test_rerank_single_candidate_returns_as_is():
    single = CANDIDATES[:1]
    out = rerank("查询", single, content_getter=_getter, api_url="http://rr:8102")
    assert out is single


def test_rerank_drops_missing_content(monkeypatch):
    def getter(unit_ids):
        return {1: "内容一", 2: "内容二"}  # 3 无内容 → 丢弃

    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return _FakeResp([0.9, 0.1])

    monkeypatch.setattr(httpx, "post", fake_post)
    out = rerank("查询", CANDIDATES, content_getter=getter, api_url="http://rr:8102", top=5)
    assert captured["json"]["sentence_pairs"] == [["查询", "内容一"], ["查询", "内容二"]]
    assert [d["unit_id"] for d in out] == [1, 2]
    assert 3 not in [d["unit_id"] for d in out]


def test_rerank_failure_returns_original(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    out = rerank("查询", CANDIDATES, content_getter=_getter, api_url="http://rr:8102")
    assert out is CANDIDATES


def test_rerank_score_mismatch_returns_original(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _FakeResp([0.9])  # 1 条 ≠ 3 条

    monkeypatch.setattr(httpx, "post", fake_post)
    out = rerank("查询", CANDIDATES, content_getter=_getter, api_url="http://rr:8102")
    assert out is CANDIDATES
