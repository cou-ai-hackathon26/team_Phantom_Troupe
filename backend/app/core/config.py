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
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

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
    llm_rate_limit_max_wait_s: float = 20.0  # longest single wait on a 429 (Groq retry-after), per retry
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

    # Web fallback (Tavily): when local evidence is weak, search an allow-list of official sites.
    tavily_api_key: SecretStr | None = None
    web_fallback: bool = False  # switch off for offline demos or weak venue internet
    web_trigger_score: float = 0.85  # search the web when the best local dense score is below this
    web_max_results: int = 3
    web_timeout_s: float = 8.0
    # comma-separated hosts; a result is kept only if its host is one of these or a subdomain of one
    web_allowed_domains: str = (
        "bdlaws.minlaw.gov.bd,minland.gov.bd,land.gov.bd,mutation.land.gov.bd,dss.gov.bd,"
        "police.gov.bd,gd.police.gov.bd,nhrc.org.bd,ugc.gov.bd,mole.gov.bd,dife.gov.bd,bangladesh.gov.bd"
    )

    # Text-to-speech (ElevenLabs): the 🔊 button reads an answer aloud. Bangla needs eleven_v3 (or v4);
    # the API default model (multilingual_v2) has no Bangla. Free tier is ~10k characters/month, so audio
    # is cached on disk by text hash and long answers are cut at a sentence end.
    elevenlabs_api_key: SecretStr | None = None
    tts_enabled: bool = True
    tts_model_id: str = "eleven_v3"
    tts_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"  # an ElevenLabs premade voice; change after listening
    tts_output_format: str = "mp3_44100_64"
    tts_max_chars: int = 1500
    tts_timeout_s: float = 30.0
    tts_cache_dir: Path = DATA_DIR / "tts_cache"

    # OCR (local only)
    ocr_provider: str = "tesseract"
    ocr_second_engine: str = "easyocr"
    ocr_device: str = "auto"
    ocr_min_confidence: float = 70.0

    health_check_timeout_s: float = 5.0

    # Admin panel (knowledge management): admins log in with email + password (admin_users table).
    # APP_SECRET_KEY signs login sessions; ADMIN_TOKEN is an optional extra key for scripts.
    app_secret_key: SecretStr | None = None
    admin_session_hours: int = 12
    admin_token: SecretStr | None = None
    max_upload_mb: int = 25

    # Personal documents uploaded by users: kept in memory only, never embedded or stored.
    user_doc_ttl_minutes: int = 60
    user_doc_max_count: int = 200

    # Official-source conflict detection (services/conflict_disclosure.py); false = answers exactly as before
    conflict_detection: bool = True

    # Follow-up conversations: kept in this process's memory only (services/conversation_store.py).
    conversation_ttl_minutes: int = 120  # sliding: each answered turn extends it
    conversation_max_count: int = 1000  # oldest conversations are evicted beyond this
    conversation_history_exchanges: int = 3  # earlier question/answer pairs shown to Call 1 (token budget)
    conversation_max_reused_sources: int = 3  # earlier cited chunks that may be reused in one answer

    @field_validator(
        "database_url",
        "qdrant_url",
        "qdrant_api_key",
        "groq_api_key",
        "llm_model",
        "admin_token",
        "app_secret_key",
        "elevenlabs_api_key",
        mode="before",
    )
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
