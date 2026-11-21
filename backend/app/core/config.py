"""Application settings, read only from the repo-root .env via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Supabase PostgreSQL (session pooler URL with +asyncpg)
    database_url: SecretStr | None = None

    # Qdrant Cloud
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "adhikarai_chunks"

    # Groq
    groq_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 3
    stt_model: str = "whisper-large-v3"

    # Embeddings (local)
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768
    embedding_device: str = "auto"  # auto | cuda | cpu

    # Retrieval
    retrieval_min_score: float = 0.80
    dense_top_k: int = 20
    bm25_top_k: int = 20
    fused_top_k: int = 5
    rrf_k: int = 60
    bm25_path: Path = DATA_DIR / "index" / "bm25.pkl"

    # OCR (local only)
    ocr_provider: str = "tesseract"
    ocr_second_engine: str = "easyocr"
    ocr_device: str = "auto"
    ocr_min_confidence: float = 70.0

    health_check_timeout_s: float = 5.0

    @field_validator("database_url", "qdrant_url", "qdrant_api_key", "groq_api_key", "llm_model", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Treat empty .env entries (e.g. `GROQ_API_KEY=`) as not configured."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
