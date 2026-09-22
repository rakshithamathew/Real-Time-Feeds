from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    frontend_origin: str = "http://localhost:5173"
    database_url: str = (
        "postgresql+asyncpg://incident_feed:incident_feed@localhost:5432/incident_feed"
    )
    test_database_url: str = (
        "postgresql+asyncpg://incident_feed:incident_feed@localhost:5433/incident_feed_test"
    )


settings = Settings()
