from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg://localhost/onboarder"
    TEST_DATABASE_URL: str | None = None
    ANALYSIS_ROOT: Path = REPOSITORY_ROOT
    MAX_FILE_BYTES: int = Field(default=1_048_576, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
