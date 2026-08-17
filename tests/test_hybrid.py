"""混合检索：BM25 与向量分数融合；FTS 同步与检索。"""

from app.database import get_connection
from app.knowledge.crud import create_unit
from app.knowledge.fts import FtsStore, fuse_scores, hybrid_search


def test_fuse_scores_weighted_combination():
    bm25 = {1: 0.9, 2: 0.1}
    vec = {1: 0.5, 2: 0.8}
    fused = fuse_scores(bm25, vec, w_bm25=0.4, w_vec=0.6)
    # 向量权重更高，向量侧明显占优的单元 2 应胜出
    assert fused[2] > fused[1]
    assert 0 <= fused[1] <= 1


def test_fuse_scores_keeps_single_source_units():
    bm25 = {1: 0.9}
    vec = {2: 0.7}
    fused = fuse_scores(bm25, vec, w_bm25=0.5, w_vec=0.5)
    assert fused[1] > 0 and fused[2] > 0


def test_fts_returns_matching_unit(db):
    with get_connection() as conn:
        uid = create_unit(conn, title="绿色建筑", content="绿色建筑评价标准包含安全耐久、健康舒适等维度。", creator_id=1)
        FtsStore.sync_unit(conn, uid)
    hits = FtsStore.search("安全耐久", top_k=3)
    assert any(int(h["unit_id"]) == uid for h in hits)


def test_fts_delete_removes_index(db):
    with get_connection() as conn:
        uid = create_unit(conn, title="双碳", content="双碳目标指 2030 年碳达峰。", creator_id=1)
        FtsStore.sync_unit(conn, uid)
        FtsStore.sync_delete(conn, [uid])
    hits = FtsStore.search("碳达峰", top_k=3)
    assert all(int(h["unit_id"]) != uid for h in hits)


def test_hybrid_search_returns_fused_results(db):
    with get_connection() as conn:
        uid1 = create_unit(conn, title="绿色建筑评价", content="绿色建筑评价标准包含安全耐久、健康舒适、生活便利、资源节约、环境宜居。", creator_id=1)
        uid2 = create_unit(conn, title="防火设计", content="建筑防火设计核心是控制火灾蔓延与保障疏散。", creator_id=1)
        FtsStore.sync_unit(conn, uid1)
        FtsStore.sync_unit(conn, uid2)
    results = hybrid_search("绿色建筑 安全耐久", top_k=3)
    ids = [int(r["unit_id"]) for r in results]
    assert uid1 in ids
