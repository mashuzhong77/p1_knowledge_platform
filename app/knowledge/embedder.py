"""文本向量化：优先 sentence-transformers，不可用时降级 n-gram hash 向量。"""

import hashlib
import math


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
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name
        self._model = None
        if model_name and model_name != "hash":
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(model_name)
            except Exception:
                self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is not None:
            vecs = self._model.encode(list(texts), normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        return [_hash_embed(t) for t in texts]


_EMBEDDER: Embedder | None = None


def get_embedder() -> Embedder:
    global _EMBEDDER
    if _EMBEDDER is None:
        _EMBEDDER = Embedder()
    return _EMBEDDER
