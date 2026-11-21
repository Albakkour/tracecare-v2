"""Application configuration, read from environment variables (and an optional .env file).

All secrets are read server-side only. Nothing in this module should ever be logged verbatim.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single place where the default model identifier lives. Override with ANTHROPIC_MODEL.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default=DEFAULT_ANTHROPIC_MODEL, alias="ANTHROPIC_MODEL")
    # Effort controls how much the model thinks; "medium" balances latency and extraction quality.
    anthropic_effort: str = Field(default="medium", alias="ANTHROPIC_EFFORT")
    llm_timeout_seconds: float = Field(default=120.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_output_tokens: int = Field(default=16000, alias="LLM_MAX_OUTPUT_TOKENS")

    database_url: str = Field(default="sqlite:///./tracecare.db", alias="DATABASE_URL")
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", alias="CORS_ORIGINS")

    demo_mode_enabled: bool = Field(default=True, alias="DEMO_MODE_ENABLED")
    demo_access_password: str = Field(default="", alias="DEMO_ACCESS_PASSWORD")
    max_transcript_chars: int = Field(default=30000, alias="MAX_TRANSCRIPT_CHARS")
    # Format: "<count>/<minute|hour|day>" per client IP, e.g. "20/hour". Empty disables the limit.
    analysis_rate_limit: str = Field(default="20/hour", alias="ANALYSIS_RATE_LIMIT")
    # Secret used to sign demo-gate sessions and hash client IPs for rate limiting. Required in production
    # (serverless instances must share it). Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    session_secret: str = Field(default="", alias="SESSION_SECRET")
    # Saved encounters older than this are deleted automatically (0 disables).
    encounter_retention_days: int = Field(default=7, alias="ENCOUNTER_RETENTION_DAYS")
    # Set automatically by Vercel ("1"); switches the database layer to serverless-friendly settings.
    vercel: str = Field(default="", alias="VERCEL")
    # Set SERVERLESS=true explicitly on serverless hosts (does not depend on Vercel system variables).
    serverless: bool = Field(default=False, alias="SERVERLESS")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_serverless(self) -> bool:
        return self.serverless or bool(self.vercel)

    def production_problems(self) -> list[str]:
        """Configuration problems that make a production deployment unsafe or broken."""
        problems = []
        if self.sqlalchemy_database_url.startswith("sqlite"):
            problems.append("DATABASE_URL is SQLite; use PostgreSQL (Supabase/Neon) in production.")
        if not self.session_secret or len(self.session_secret) < 32:
            problems.append("SESSION_SECRET is missing or shorter than 32 characters.")
        if not self.cors_origin_list:
            problems.append("CORS_ORIGINS is empty.")
        if not self.available_providers():
            problems.append("No provider: set ANTHROPIC_API_KEY or DEMO_MODE_ENABLED=true.")
        return problems

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip() and o.strip() != "*"]

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def available_providers(self) -> list[str]:
        providers: list[str] = []
        if self.anthropic_configured:
            providers.append("anthropic")
        if self.demo_mode_enabled:
            providers.append("demo")
        return providers

    def default_provider(self) -> str | None:
        available = self.available_providers()
        return available[0] if available else None

    def rate_limit(self) -> tuple[int, int] | None:
        """Return (max_requests, window_seconds) or None when disabled."""
        value = self.analysis_rate_limit.strip().lower()
        if not value or value in {"0", "off", "none", "disabled"}:
            return None
        match = re.fullmatch(r"(\d+)\s*/\s*(second|minute|hour|day)", value)
        if not match:
            raise ValueError("ANALYSIS_RATE_LIMIT must look like '20/hour'")
        windows = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
        return int(match.group(1)), windows[match.group(2)]

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url.strip()
        # Supabase / Railway give postgres:// or postgresql:// URLs; use the psycopg 3 driver.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
