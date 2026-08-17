"""向量存储：优先 ChromaDB，缺失时 JSON 文件降级（同接口）。"""

import json
import math
from pathlib import Path

from ..config import settings


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / ((na * nb) or 1e-9)


class JsonVectorStore:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"ids": [], "texts": [], "vectors": [], "metadatas": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def add(self, ids, texts, vectors, metadatas) -> None:
        self.data["ids"].extend(ids)
        self.data["texts"].extend(texts)
        self.data["vectors"].extend(vectors)
        self.data["metadatas"].extend(metadatas)
        self._save()

    def delete(self, ids) -> None:
        idset = {str(i) for i in ids}
        keep = [i for i in range(len(self.data["ids"])) if str(self.data["ids"][i]) not in idset]
        for key in self.data:
            self.data[key] = [self.data[key][i] for i in keep]
        self._save()

    def query(self, vector, top_k: int = 5) -> list[dict]:
        scored = sorted(
            ((_cosine(vector, v), i) for i, v in enumerate(self.data["vectors"])),
            key=lambda t: t[0],
            reverse=True,
        )
        return [
            {
                "id": self.data["ids"][i],
                "text": self.data["texts"][i],
                "metadata": self.data["metadatas"][i],
                "score": round(s, 4),
            }
            for s, i in scored[:top_k]
        ]


class ChromaVectorStore:
    def __init__(self, path):
        import chromadb

        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            "kb_units", metadata={"hnsw:space": "cosine"}
        )

    def add(self, ids, texts, vectors, metadatas) -> None:
        self.collection.add(
            ids=[str(i) for i in ids],
            documents=texts,
            embeddings=vectors,
            metadatas=metadatas,
        )

    def delete(self, ids) -> None:
        for i in ids:
            try:
                self.collection.delete(ids=[str(i)])
            except Exception:
                pass

    def query(self, vector, top_k: int = 5) -> list[dict]:
        res = self.collection.query(
            query_embeddings=[vector], n_results=top_k, include=["documents", "metadatas", "distances"]
        )
        out = []
        if res and res.get("ids") and res["ids"][0]:
            for i in range(len(res["ids"][0])):
                out.append(
                    {
                        "id": res["ids"][0][i],
                        "text": res["documents"][0][i],
                        "metadata": res["metadatas"][0][i] or {},
                        "score": round(1 - res["distances"][0][i], 4),
                    }
                )
        return out


_STORE = None


def get_vectorstore():
    global _STORE
    if _STORE is None:
        try:
            _STORE = ChromaVectorStore(settings.vector_dir)
        except Exception:
            _STORE = JsonVectorStore(settings.vector_dir / "vectors.json")
    return _STORE
