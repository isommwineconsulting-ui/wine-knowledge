"""Configuration and the shared Supabase client.

Reads settings from environment variables (optionally via a local .env file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from a .env file if present

DEFAULT_USER_AGENT = (
    "wine-knowledge-bot/0.1 "
    "(+https://github.com/isommwineconsulting-ui/wine-knowledge)"
)


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    bucket: str
    user_agent: str
    request_delay_seconds: float


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_ROLE_KEY", key),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill them in."
        )

    delay_raw = os.environ.get("WINE_SCRAPER_DELAY_SECONDS", "1.0").strip()
    try:
        delay = float(delay_raw)
    except ValueError:
        delay = 1.0

    return Settings(
        supabase_url=url,
        supabase_service_role_key=key,
        bucket=os.environ.get("WINE_PDF_BUCKET", "wine-pdfs").strip() or "wine-pdfs",
        user_agent=os.environ.get("WINE_SCRAPER_USER_AGENT", DEFAULT_USER_AGENT).strip()
        or DEFAULT_USER_AGENT,
        request_delay_seconds=delay,
    )


@lru_cache(maxsize=1)
def get_supabase():
    """Return a cached Supabase client authenticated with the service-role key."""
    from supabase import create_client

    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
