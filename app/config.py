"""应用配置（pydantic-settings，支持 .env 覆盖）。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "P1 知识库管理平台"
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: Path = BASE_DIR / "data" / "db.sqlite3"
    knowledge_dir: Path = BASE_DIR / "data" / "knowledge"
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    vector_dir: Path = BASE_DIR / "data" / "vectors"
    embedding_model: str = "hash"  # "hash"=本地 n-gram 降级；本地 sentence-transformers 名；远程服务用 embedding_api_url
    # ===== LLM 通用配置（主配置；P3 微调模型接入时填 vLLM 地址/模型名） =====
    llm_api_key: str = ""  # 非空 = 在线（全链路在线/离线判据，见 effective_llm_api_key）
    llm_base_url: str = ""  # 空则回退 deepseek_base_url
    llm_model: str = ""  # 空则回退 deepseek_model
    # ===== 遗留别名(deprecated)：新配置一律用 LLM_*，deepseek_* 仅作回退兼容 =====
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # ===== 远程向量/重排服务（P3 GPU 云服务器：BGE-M3 / BGE-reranker） =====
    embedding_api_url: str = ""  # 非空则 embedding 走远程 POST {url}/v1/embeddings（取 dense）
    embedding_api_key: str = ""
    rerank_api_url: str = ""  # 非空则问答阶段启用 rerank：POST {url}/v1/rerank（sentence_pairs）
    rerank_api_key: str = ""
    rerank_top: int = 20  # rerank 输入候选上限；rerank 未启用时无影响
    top_k: int = 5
    # ===== 检索参数（RRF / 混合检索权重 / 召回量 / MMR，均可配） =====
    rrf_k: int = 60  # RRF 融合常数 k（与 retrieval.py 默认一致）
    w_bm25: float = 0.4  # 混合检索 BM25 权重（fuse_scores）
    w_vec: float = 0.6  # 混合检索向量权重（fuse_scores）
    recall_multiplier: int = 2  # 每路召回量 = top_k * recall_multiplier
    mmr_enabled: bool = False  # MMR 去冗余开关（默认关，不改变现有行为）
    mmr_lambda: float = 0.7  # MMR 相关度/多样性权衡
    mmr_top: int = 5  # MMR 输出上限；0 时用 top_k
    # 无关话题拒答：离线（无 key）时 BM25 无命中且向量相似度低于此值 → 拒答
    min_offline_similarity: float = 0.35
    # ===== P0 安全 =====
    session_ttl_seconds: int = 7200
    cors_origins: list[str] = []  # env 传 JSON：CORS_ORIGINS=["http://127.0.0.1:8000"]
    max_upload_size_mb: int = 50  # 现有最大文件 21.2MB，默认 50 覆盖
    max_text_chars: int = 200_000
    enable_docs: bool = True
    force_https_headers: bool = False  # 置于 TLS 反向代理后时置 true（启用 HSTS）

    # ===== 生效配置（LLM_* 优先，未填回退 deepseek_* 遗留别名） =====
    @property
    def effective_llm_api_key(self) -> str:
        return self.llm_api_key or self.deepseek_api_key

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url or self.deepseek_base_url

    @property
    def effective_llm_model(self) -> str:
        return self.llm_model or self.deepseek_model


settings = Settings()
