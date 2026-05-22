from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Mongo + MinIO + ARQ defaults (single-compose stack)."""

    ENV: Literal["dev", "stage", "prod"] = "dev"

    MONGO_URI: str = "mongodb://127.0.0.1:27017"
    MONGO_DB: str = "gradelab"

    STORAGE_BACKEND: Literal["minio"] = "minio"
    STORAGE_MANAGER_URL: str = "http://127.0.0.1:8081"
    STORAGE_MANAGER_TOKEN: str | None = None

    RUN_EXECUTOR: Literal["arq"] = "arq"
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    ARQ_QUEUE_NAME: str = "gradelab:arq"
    INTERNAL_API_TOKEN: str | None = None
    LLMPROXY_URL: str | None = None
    LLMPROXY_SERVICE_TOKEN: str | None = None

    ANYTASK_USERNAME: str | None = None
    ANYTASK_PASSWORD: str | None = None

    DATA_DIR: Path = Path("data")

    CORS_ORIGINS: str = ""

    PROD_PUBLIC_AUTH: bool = False

    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    #: When the ARQ worker runs ``docker run`` *inside* a container, volume ``-v`` paths must be
    #: **host** paths (the Docker daemon resolves them on the host). Example: ``/home/you/proj/gradelab/data``.
    DOCKER_HOST_DATA_DIR: str | None = None
    DOCKER_HOST_PIPELINES_DIR: str | None = None

    @field_validator("DATA_DIR", mode="before")
    @classmethod
    def coerce_data_dir(cls, v: object) -> Path:
        return Path(v) if not isinstance(v, Path) else v

    @property
    def cors_origins_list(self) -> list[str]:
        raw = (self.CORS_ORIGINS or "").strip()
        if not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def REALMS_DIR(self) -> Path:
        return self.DATA_DIR / "realms"

    @property
    def PIPELINE_VENVS_DIR(self) -> Path:
        return self.DATA_DIR / "pipeline_venvs"

    @property
    def RUNS_DIR(self) -> Path:
        return self.DATA_DIR / "runs"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
