from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    demo_mode: bool = False
    openai_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/fitness_coach"

    # Set QDRANT_URL to use the Qdrant server; otherwise the embedded on-disk mode at QDRANT_PATH is used.
    qdrant_url: str | None = None
    qdrant_path: str = "./qdrant_data"
    qdrant_collection: str = "protocols"
    rag_top_k: int = 3

    # Off for local use. When on, every /users and /ask request needs `Authorization: Bearer <token>`
    # (issued by scripts/issue_token.py) and can only touch the token owner's data.
    auth_enabled: bool = False
    ask_rate_limit_per_minute: int = 20
    openai_timeout_seconds: float = 30.0

    # Integrations. Each provider is enabled only when its credentials are set.
    # TOKEN_ENCRYPTION_KEY encrypts stored OAuth tokens; generate with scripts/generate_key.py.
    token_encryption_key: str = ""
    public_api_url: str = "http://localhost:8000"
    ui_url: str = "http://localhost:8501"
    google_client_id: str = ""
    google_client_secret: str = ""
    fatsecret_consumer_key: str = ""
    fatsecret_consumer_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
