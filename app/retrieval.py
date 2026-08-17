"""检索增强：HyDE 支路、RRF 融合与动态断崖截断（框架 R3/R4，蒸馏自 ai_0302）。"""

from .llm import chat_completion
from .prompts import load_prompt

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
