from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "gradelab"
    LLMPROXY_SERVICE_TOKEN: str = ""
    OPENAI_COMPAT_BASE: str = "https://api.openai.com/v1"
    LOG_FULL_PAYLOADS: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
