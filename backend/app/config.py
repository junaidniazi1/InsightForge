from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    supabase_anon_key: str = ""
    supabase_service_role_key: str
    # Optional since Phase 8A: new Supabase projects sign tokens with asymmetric
    # keys verified via JWKS. The secret remains for legacy projects (HS256).
    supabase_jwt_secret: str = ""

    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-sonnet-4-6"
    anthropic_heavy_model: str = "claude-opus-4-7"

    # Phase 5 — Gemini (free-tier Flash)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 200 * 1024 * 1024

    # Phase 8B — DB Connectors
    db_encryption_key: str = ""
    dev_allow_private_db_hosts: bool = False
    db_import_max_rows: int = 1_000_000

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
