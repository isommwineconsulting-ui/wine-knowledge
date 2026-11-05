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
    owner_id: str
    allowed_hosts: tuple[str, ...]
    max_pdf_bytes: int
    max_html_bytes: int


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

    owner_id = os.environ.get("WINE_PDF_OWNER_ID", "").strip()
    import uuid
    try:
        owner_id = str(uuid.UUID(owner_id))
    except (ValueError, AttributeError):
        raise ConfigError("WINE_PDF_OWNER_ID must be a valid authorized user UUID")

    allowed_hosts = tuple(sorted({
        h.strip().lower().rstrip(".")
        for h in os.environ.get("WINE_ALLOWED_HOSTS", "").split(",")
        if h.strip()
    }))
    try:
        max_pdf_bytes = int(os.environ.get("WINE_MAX_PDF_BYTES", "52428800"))
        max_html_bytes = int(os.environ.get("WINE_MAX_HTML_BYTES", "2097152"))
        if not (0 < max_pdf_bytes <= 209715200 and 0 < max_html_bytes <= 10485760):
            raise ValueError("out of bounds")
    except ValueError:
        raise ConfigError("Invalid WINE_MAX_PDF_BYTES or WINE_MAX_HTML_BYTES")

    return Settings(
        supabase_url=url,
        supabase_service_role_key=key,
        bucket=os.environ.get("WINE_PDF_BUCKET", "wine-pdfs").strip() or "wine-pdfs",
        user_agent=os.environ.get("WINE_SCRAPER_USER_AGENT", DEFAULT_USER_AGENT).strip()
        or DEFAULT_USER_AGENT,
        request_delay_seconds=delay,
        owner_id=owner_id,
        allowed_hosts=allowed_hosts,
        max_pdf_bytes=max_pdf_bytes,
        max_html_bytes=max_html_bytes,
    )


@lru_cache(maxsize=1)
def get_supabase():
    """Return a cached Supabase client authenticated with the service-role key."""
    from supabase import create_client

    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
