"""配置解析：LLM_* 主配置优先，deepseek_* 遗留别名回退。"""

from app.config import Settings


def test_effective_uses_llm_fields_when_set():
    s = Settings(
        llm_api_key="sk-llm",
        llm_base_url="http://vllm:8100/v1",
        llm_model="finetuned-qwen",
        _env_file=None,
    )
    assert s.effective_llm_api_key == "sk-llm"
    assert s.effective_llm_base_url == "http://vllm:8100/v1"
    assert s.effective_llm_model == "finetuned-qwen"


def test_effective_falls_back_to_deepseek_aliases():
    s = Settings(
        llm_api_key="",
        llm_base_url="",
        llm_model="",
        deepseek_api_key="sk-ds",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        _env_file=None,
    )
    assert s.effective_llm_api_key == "sk-ds"
    assert s.effective_llm_base_url == "https://api.deepseek.com"
    assert s.effective_llm_model == "deepseek-chat"


def test_effective_offline_when_both_empty():
    s = Settings(_env_file=None)
    assert s.effective_llm_api_key == ""
    assert s.effective_llm_model == "deepseek-chat"  # base_url/model 有默认值，只有 key 是判据


def test_embedding_default_is_hash():
    s = Settings(_env_file=None)
    assert s.embedding_model == "hash"
