"""Download PDF files to a local path and compute their content hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .config import get_settings

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


def download(url: str, dest_dir: Path) -> DownloadedFile:
    """Stream ``url`` to ``dest_dir``, returning path/hash/size.

    Raises ValueError if the response is not a PDF.
    """
    settings = get_settings()
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = filename_from_url(url)
    dest = dest_dir / filename

    hasher = hashlib.sha256()
    size = 0
    first_chunk = True
    with httpx.Client(
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
        timeout=60.0,
    ) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    if not chunk:
                        continue
                    if first_chunk:
                        if not chunk.startswith(PDF_MAGIC):
                            fh.close()
                            dest.unlink(missing_ok=True)
                            raise ValueError(
                                f"{url} did not return a PDF (bad magic bytes)."
                            )
                        first_chunk = False
                    hasher.update(chunk)
                    size += len(chunk)
                    fh.write(chunk)

    return DownloadedFile(
        path=dest,
        sha256=hasher.hexdigest(),
        size_bytes=size,
        filename=filename,
    )
