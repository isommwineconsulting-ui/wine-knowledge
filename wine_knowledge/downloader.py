"""Download bounded PDF files from approved public HTTPS hosts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .config import get_settings
from .netpolicy import MAX_REDIRECTS, validate_source_url, validated_redirect

PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class DownloadedFile:
    path: Path
    sha256: str
    size_bytes: int
    filename: str


def filename_from_url(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or "document.pdf"


def inspect_local(path: Path) -> DownloadedFile:
    """Hash and size an existing local PDF, validating its magic bytes."""
    with path.open("rb") as fh:
        header = fh.read(len(PDF_MAGIC))
        if header != PDF_MAGIC:
            raise ValueError(f"{path} is not a PDF (bad magic bytes).")
        hasher = hashlib.sha256()
        hasher.update(header)
        size = len(header)
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
            size += len(chunk)
    return DownloadedFile(path=path, sha256=hasher.hexdigest(),
                          size_bytes=size, filename=path.name)


def download(url: str, dest_dir: Path) -> DownloadedFile:
    """Verify each redirect and enforce a hard PDF size ceiling."""
    settings = get_settings()
    current = validate_source_url(url, settings.allowed_hosts)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = filename_from_url(url)
    dest = dest_dir / filename

    # Prevent a partial download from being treated as a valid local PDF.
    with httpx.Client(
        headers={"User-Agent": settings.user_agent},
        follow_redirects=False,
        trust_env=False,
        timeout=60.0,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            current = validate_source_url(current, settings.allowed_hosts)
            with client.stream("GET", current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = validated_redirect(
                        current, response.headers.get("location", ""),
                        settings.allowed_hosts,
                    )
                    continue
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > settings.max_pdf_bytes:
                    raise ValueError("PDF exceeds configured byte limit")

                digest = hashlib.sha256()
                size = 0
                header = b""
                try:
                    with dest.open("wb") as fh:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > settings.max_pdf_bytes:
                                raise ValueError("PDF exceeds configured byte limit")
                            if len(header) < len(PDF_MAGIC):
                                header = (header + chunk)[:len(PDF_MAGIC)]
                                if len(header) == len(PDF_MAGIC) and header != PDF_MAGIC:
                                    raise ValueError("Invalid PDF magic bytes")
                            digest.update(chunk)
                            fh.write(chunk)
                    if header != PDF_MAGIC:
                        raise ValueError("Empty or invalid PDF")
                except Exception:
                    dest.unlink(missing_ok=True)
                    raise
                return DownloadedFile(dest, digest.hexdigest(), size, filename)
        raise ValueError("Too many redirects")
