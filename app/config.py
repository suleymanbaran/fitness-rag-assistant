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


@lru_cache
def get_settings() -> Settings:
    return Settings()
