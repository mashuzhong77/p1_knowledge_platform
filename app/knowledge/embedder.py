"""文本向量化：远程 BGE-M3(dense) > 本地 sentence-transformers > n-gram hash 降级。

远程（embedding_api_url 非空）失败时**响亮抛错**、不静默降级：
查询侧调用方已有 try/except 自动降级到 BM25；导入侧由 importer 转成清晰报错。
"""

import hashlib
import math

from ..config import settings

REMOTE_BATCH_SIZE = 64


def _hash_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    s = (text or "").lower()
    for n in (1, 2, 3):
        for i in range(max(0, len(s) - n + 1)):
            gram = s[i : i + n]
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16)
            vec[h % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class Embedder:
    def __init__(self, api_url: str = "", api_key: str = "", model_name: str = ""):
        self._cfg = (api_url, api_key, model_name)
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name
        self._model = None
        if not api_url and model_name and model_name != "hash":
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(model_name)
            except Exception:
                self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.api_url:
            return self._embed_remote(texts)
        if self._model is not None:
            vecs = self._model.encode(list(texts), normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        return [_hash_embed(t) for t in texts]

    def _embed_remote(self, texts: list[str]) -> list[list[float]]:
        import httpx

        url = f"{self.api_url}/v1/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        out: list[list[float]] = []
        for i in range(0, len(texts), REMOTE_BATCH_SIZE):
            batch = texts[i : i + REMOTE_BATCH_SIZE]
            resp = httpx.post(
                url,
                json={"embedding_documents": batch},
                headers=headers,
                timeout=120,
            )
            resp.raise_for_status()
            dense = resp.json()["dense"]  # BGE-M3 契约：{"dense": [[...]], "sparse": [...]}
            if len(dense) != len(batch):
                raise RuntimeError(
                    f"远程向量服务返回条数不符：{len(dense)} != {len(batch)}（{url}）"
                )
            out.extend(dense)
        return out


_EMBEDDER: Embedder | None = None


def get_embedder() -> Embedder:
    """单例：配置键 (api_url, api_key, model_name) 变化时重建，避免用旧配置。"""
    global _EMBEDDER
    cfg = (settings.embedding_api_url, settings.embedding_api_key, settings.embedding_model)
    if _EMBEDDER is None or _EMBEDDER._cfg != cfg:
        _EMBEDDER = Embedder(api_url=cfg[0], api_key=cfg[1], model_name=cfg[2])
    return _EMBEDDER
