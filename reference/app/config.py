from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/fitness_rag"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "recovery_protocols"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
