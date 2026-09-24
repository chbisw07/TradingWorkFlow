from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from twf import __version__

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TWF_", env_file=".env", extra="ignore", frozen=True
    )

    environment: Environment = "development"
    service_name: str = Field(default="twf-api", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    service_version: str = Field(default=__version__, pattern=r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
    api_version: Literal["v1"] = "v1"
    api_prefix: Literal["/api/v1"] = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    cors_origins: tuple[str, ...] | None = None
    database_url: str = Field(default="sqlite+pysqlite:///./twf.db", repr=False)

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: tuple[str, ...] | None) -> tuple[str, ...] | None:
        for origin in origins or ():
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.path
                or url.query
                or url.fragment
                or any(c.isspace() for c in origin)
                or "*" in origin
            ):
                raise ValueError(
                    "CORS requires explicit HTTP(S) origins without paths or credentials"
                )
            _ = url.port
        return origins

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        if self.cors_origins is not None:
            return self.cors_origins
        return ("http://localhost:3000",) if self.environment == "development" else ()

    @property
    def effective_log_level(self) -> str:
        return self.log_level or ("DEBUG" if self.environment == "development" else "INFO")
