"""Upload PDF files to the Supabase Storage bucket."""

from __future__ import annotations

from pathlib import Path

from .config import get_settings, get_supabase


def storage_path_for(sha256: str, filename: str) -> str:
    """Deterministic object path: shard by hash prefix, keep original name."""
    safe_name = filename.replace("/", "_")
    return f"{sha256[:2]}/{sha256}/{safe_name}"


def upload_pdf(local_path: Path, sha256: str, filename: str) -> str:
    """Upload the file and return its storage path. Idempotent on re-runs."""
    settings = get_settings()
    client = get_supabase()
    object_path = storage_path_for(sha256, filename)

    with local_path.open("rb") as fh:
        data = fh.read()

    client.storage.from_(settings.bucket).upload(
        path=object_path,
        file=data,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return object_path
