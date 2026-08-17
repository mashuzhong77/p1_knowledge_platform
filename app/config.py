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
    embedding_model: str = "BAAI/bge-m3"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    top_k: int = 5
    # 无关话题拒答：离线（无 key）时 BM25 无命中且向量相似度低于此值 → 拒答
    min_offline_similarity: float = 0.35
    # ===== P0 安全 =====
    session_ttl_seconds: int = 7200
    cors_origins: list[str] = []  # env 传 JSON：CORS_ORIGINS=["http://127.0.0.1:8000"]
    max_upload_size_mb: int = 50  # 现有最大文件 21.2MB，默认 50 覆盖
    max_text_chars: int = 200_000
    enable_docs: bool = True
    force_https_headers: bool = False  # 置于 TLS 反向代理后时置 true（启用 HSTS）


settings = Settings()
