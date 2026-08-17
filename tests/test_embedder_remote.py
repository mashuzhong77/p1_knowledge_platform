"""远程 BGE-M3 embedding：请求格式、dense 提取、分批、条数校验与响亮失败。"""

import httpx

from app.knowledge.embedder import Embedder


class _FakeResp:
    def __init__(self, dense):
        self._dense = dense

    def raise_for_status(self):
        pass

    def json(self):
        return {"dense": self._dense}


def test_embed_remote_sends_embedding_documents(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResp([[0.1, 0.2], [0.3, 0.4]])

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = Embedder(api_url="http://bge:8101", api_key="sk-1")
    out = emb.embed(["a", "b"])
    assert captured["url"] == "http://bge:8101/v1/embeddings"
    assert captured["json"] == {"embedding_documents": ["a", "b"]}
    assert captured["headers"] == {"Authorization": "Bearer sk-1"}
    assert out == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_remote_batches_by_64(monkeypatch):
    batches = []

    def fake_post(url, json=None, headers=None, timeout=None):
        batches.append(json["embedding_documents"])
        return _FakeResp([[1.0]] * len(batches[-1]))

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = Embedder(api_url="http://bge:8101")
    out = emb.embed([f"t{i}" for i in range(130)])
    assert [len(b) for b in batches] == [64, 64, 2]
    assert len(out) == 130


def test_embed_remote_raises_on_connection_error(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = Embedder(api_url="http://bge:8101")
    try:
        emb.embed(["a"])
        assert False, "should raise"
    except httpx.ConnectError:
        pass


def test_embed_remote_raises_on_count_mismatch(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return _FakeResp([[1.0]])  # 只返回 1 条，输入 2 条

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = Embedder(api_url="http://bge:8101")
    try:
        emb.embed(["a", "b"])
        assert False, "should raise"
    except RuntimeError as e:
        assert "条数不符" in str(e)


def test_embed_empty_does_not_call_remote(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        raise AssertionError("空输入不应发起远程请求")

    monkeypatch.setattr(httpx, "post", fake_post)
    emb = Embedder(api_url="http://bge:8101")
    assert emb.embed([]) == []


def test_embed_hash_when_no_api_url():
    emb = Embedder(api_url="", model_name="hash")
    out = emb.embed(["绿建"])
    assert len(out) == 1
    assert len(out[0]) == 256
