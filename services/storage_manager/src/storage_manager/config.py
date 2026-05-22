from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"
    STORAGE_MANAGER_TOKEN: str = ""
    DEFAULT_BUCKETS: str = "homeworks,runs,pipelines,realms,courses"
    MONGO_URI: str = "mongodb://127.0.0.1:27017"
    MONGO_DB: str = "gradelab"
    REALMS_BUCKET: str = "realms"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def bucket_list(self) -> list[str]:
        return [b.strip() for b in self.DEFAULT_BUCKETS.split(",") if b.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
