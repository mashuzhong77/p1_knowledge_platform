"""混合检索：SQLite FTS5（BM25）与向量检索分数融合。"""

from ..database import get_connection
from .embedder import get_embedder
from .vectorstore import get_vectorstore


class FtsStore:
    """FTS5 全文索引：trigram 分词（中文友好），随知识单元增删改同步。"""

    @staticmethod
    def ensure(conn) -> None:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5("
            "unit_id UNINDEXED, title, content, tokenize='trigram')"
        )

    @staticmethod
    def sync_unit(conn, unit_id) -> None:
        FtsStore.ensure(conn)
        row = conn.execute("SELECT title, content FROM knowledge_units WHERE id=?", (unit_id,)).fetchone()
        if row is None:
            return
        conn.execute("DELETE FROM unit_fts WHERE unit_id=?", (str(unit_id),))
        conn.execute(
            "INSERT INTO unit_fts(unit_id,title,content) VALUES(?,?,?)",
            (str(unit_id), row["title"], row["content"] or ""),
        )

    @staticmethod
    def sync_delete(conn, unit_ids) -> None:
        FtsStore.ensure(conn)
        for uid in unit_ids:
            conn.execute("DELETE FROM unit_fts WHERE unit_id=?", (str(uid),))

    @staticmethod
    def rebuild(conn) -> None:
        FtsStore.ensure(conn)
        conn.execute("DELETE FROM unit_fts")
        for row in conn.execute("SELECT id, title, content FROM knowledge_units").fetchall():
            conn.execute(
                "INSERT INTO unit_fts(unit_id,title,content) VALUES(?,?,?)",
                (str(row["id"]), row["title"], row["content"] or ""),
            )

    @staticmethod
    def search(query: str, top_k: int = 15) -> list[dict]:
        terms = _trigrams(query)
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        with get_connection() as conn:
            FtsStore.ensure(conn)
            try:
                rows = conn.execute(
                    "SELECT unit_id, bm25(unit_fts) AS s FROM unit_fts WHERE unit_fts MATCH ? ORDER BY s LIMIT ?",
                    (match, top_k),
                ).fetchall()
            except Exception:  # noqa: BLE001（查询词过短/语法问题等）
                return []
            return [{"unit_id": int(r["unit_id"]), "score": -r["s"]} for r in rows]


def _trigrams(text: str) -> list[str]:
    """将查询文本切分为重叠三元组（trigram 分词器按 3 字符索引）。"""
    cleaned = "".join(ch for ch in (text or "") if ch.isalnum())
    return [cleaned[i : i + 3] for i in range(len(cleaned) - 2)]


def _norm(scores: dict) -> dict:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def fuse_scores(bm25: dict, vec: dict, w_bm25: float = 0.4, w_vec: float = 0.6) -> dict:
    """加权融合两路分数（各自 min-max 归一化后加权求和）。"""
    nb, nv = _norm(bm25), _norm(vec)
    out: dict = {}
    for key in set(nb) | set(nv):
        out[key] = w_bm25 * nb.get(key, 0.0) + w_vec * nv.get(key, 0.0)
    return out


def hybrid_search(query: str, top_k: int = 5, w_bm25: float = 0.4, w_vec: float = 0.6) -> list[dict]:
    """混合检索：BM25 与向量双路召回后融合排序。"""
    bm25_hits = {h["unit_id"]: h["score"] for h in FtsStore.search(query, top_k=top_k * 3)}
    vec_hits: dict = {}
    try:
        embedder = get_embedder()
        store = get_vectorstore()
        for hit in store.query(embedder.embed([query])[0], top_k=top_k * 3):
            uid = hit["metadata"].get("unit_id")
            if uid:
                vec_hits[int(uid)] = hit["score"]
    except Exception:  # noqa: BLE001
        pass

    fused = fuse_scores(bm25_hits, vec_hits, w_bm25=w_bm25, w_vec=w_vec)
    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [
        {
            "unit_id": unit_id,
            "score": round(score, 4),
            "sources": [s for s, d in (("bm25", bm25_hits), ("vector", vec_hits)) if unit_id in d],
        }
        for unit_id, score in ranked
    ]
