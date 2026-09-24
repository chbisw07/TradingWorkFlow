from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TWF_", env_file=".env", extra="ignore", frozen=True
    )

    environment: Environment = "development"
    database_url: str = Field(default="sqlite+pysqlite:///./twf.db", repr=False)
