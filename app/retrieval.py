"""检索增强：HyDE 支路、RRF 融合、动态断崖截断与远程 BGE-reranker 重排（框架 R3/R4/R5）。"""

import logging

from .llm import chat_completion
from .prompts import load_prompt

logger = logging.getLogger(__name__)

RRF_K = 60


def reciprocal_rank_fusion(
    param_list: list[tuple[list[dict], float]],
    *,
    k: int = RRF_K,
    top: int = 5,
) -> list[dict]:
    """RRF：按排名 1/(k+rank) 加权融合多路召回（不依赖原始分数）。"""
    score_dict: dict = {}
    entity_dict: dict = {}
    for results, weight in param_list:
        for rank, chunk in enumerate(results or [], start=1):
            unit_id = chunk.get("unit_id")
            if unit_id is None:
                continue
            score_dict[unit_id] = score_dict.get(unit_id, 0.0) + (1.0 / (k + rank)) * weight
            entity_dict.setdefault(unit_id, chunk)
    merged = []
    for unit_id, score in score_dict.items():
        doc = dict(entity_dict[unit_id])
        doc["score"] = round(score, 6)
        merged.append(doc)
    merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return merged[:top]


def hyde_answer(question: str, llm_call=None) -> str:
    """生成 HyDE 假设答案；llm_call 为 None 或失败时返回空串（跳过 HyDE 支路）。"""
    prompt = load_prompt("hyde", rewritten_query=question)
    raw = (llm_call(prompt) if llm_call else "") or ""
    return raw.strip()


def default_hyde_call(prompt: str) -> str:
    """HyDE 生成调用（纯文本）；失败返回空串。"""
    return chat_completion(prompt, json_mode=False)


def dynamic_topk(
    chunk_list: list[dict],
    *,
    min_topk: int = 1,
    max_topk: int | None = None,
    gap_abs: float = 0.5,
    gap_ratio: float = 2.0,
) -> list[dict]:
    """分数断崖截断：相邻分数差超过阈值处截断（轻量版重排收口）。"""
    if not chunk_list:
        return []
    max_topk = min(max_topk or len(chunk_list), len(chunk_list))
    topk = max_topk
    if topk > min_topk:
        for i in range(min_topk - 1, max_topk - 1):
            s1 = chunk_list[i].get("score", 0.0)
            s2 = chunk_list[i + 1].get("score", 0.0)
            if (s1 - s2) > gap_abs or (s1 - s2) / (s1 + 1e-9) > gap_ratio:
                topk = i + 1
                break
    return chunk_list[:topk]


def rerank(
    query: str,
    candidates: list[dict],
    content_getter,
    api_url: str = "",
    api_key: str = "",
    top: int | None = None,
) -> list[dict]:
    """远程 BGE-reranker 重排：POST {url}/v1/rerank，body {"sentence_pairs": [[query, doc], ...]}。

    content_getter(unit_ids) 批量取内容，返回 {unit_id: content}。
    按 rerank 分覆盖 score 作为主排序分（保留 fused_score/rerank_score），失败时原样返回候选。
    """
    if not api_url or len(candidates) < 2:
        return candidates
    import httpx

    contents = content_getter([c.get("unit_id") for c in candidates])
    pairs, items = [], []
    for c in candidates:
        content = (contents.get(c.get("unit_id")) or "").strip()
        if not content:
            continue
        pairs.append([query, content])
        items.append(c)
    if len(pairs) < 2:
        return candidates
    try:
        resp = httpx.post(
            f"{api_url}/v1/rerank",
            json={"sentence_pairs": pairs},
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=60,
        )
        resp.raise_for_status()
        scores = resp.json()["scores"]
        if len(scores) != len(pairs):
            logger.error(f"rerank 返回分数条数不符：{len(scores)} != {len(pairs)}")
            return candidates
    except Exception:  # noqa: BLE001
        logger.exception(f"rerank failed, fallback to fused order (api_url={api_url})")
        return candidates

    out = []
    for item, score in zip(items, scores):
        d = dict(item)
        d["fused_score"] = d.get("score", 0.0)
        d["rerank_score"] = float(score)
        d["score"] = float(score)  # 覆盖为主排序分，保证 dynamic_topk 一致性
        out.append(d)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top] if top else out


def mmr_diverse(candidates: list[dict], content_getter, lambda_: float = 0.7, top: int | None = None) -> list[dict]:
    """MMR 去冗余：相关度 score 保留，多样性用字符 trigram 相似度（本地计算，零向量依赖）。

    content_getter(unit_ids) 批量取内容，返回 {unit_id: content}。
    贪心：先选最高分候选，再逐次选 lambda*rel - (1-lambda)*max_sim 最大者。
    不改变候选 dict 的 score/fused_score/rerank_score 字段契约。
    """
    if len(candidates) < 2:
        return candidates
    contents = content_getter([c.get("unit_id") for c in candidates])
    pool = [c for c in candidates if (contents.get(c.get("unit_id")) or "").strip()]
    if len(pool) < 2:
        return candidates
    first = max(pool, key=lambda c: c.get("score", 0.0))
    selected = [first]
    pool = [c for c in pool if c is not first]
    while pool and (top is None or len(selected) < top):
        best, best_val = None, -1e9
        for c in pool:
            sim = max(
                _trigram_similarity(contents[c["unit_id"]], contents[s["unit_id"]]) for s in selected
            )
            val = lambda_ * c.get("score", 0.0) - (1 - lambda_) * sim
            if val > best_val:
                best, best_val = c, val
        selected.append(best)
        pool.remove(best)
    return selected


def _trigram_similarity(a: str, b: str) -> float:
    sa = {a[i : i + 3] for i in range(len(a) - 2)} if len(a) >= 3 else {a or ""}
    sb = {b[i : i + 3] for i in range(len(b) - 2)} if len(b) >= 3 else {b or ""}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
