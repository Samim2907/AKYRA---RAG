from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    llm_provider: Literal["openai", "grok", "groq"] = "openai"
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    xai_api_key: str | None = None
    xai_model: str = "grok-4.7"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    enable_web_fallback: bool = True
    chunk_size: int = 900
    chunk_overlap: int = 150
    dense_candidates: int = 20
    bm25_candidates: int = 20
    rerank_candidates: int = 10
    max_crawl_pages: int = 25
    request_timeout_seconds: float = 20


settings = Settings()
