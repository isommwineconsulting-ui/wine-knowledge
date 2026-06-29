"""Extract per-page text and basic metadata from a PDF using pypdf."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader


@dataclass
class ExtractedPdf:
    title: str | None
    author: str | None
    num_pages: int
    pages: list[str] = field(default_factory=list)  # text per page, 0-indexed


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value or None


def _title_from_filename(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").strip()
    return stem or path.name


def extract(path: Path) -> ExtractedPdf:
    """Read a PDF and return its metadata plus text for each page."""
    reader = PdfReader(str(path))

    meta = reader.metadata
    title = _clean(getattr(meta, "title", None)) if meta else None
    author = _clean(getattr(meta, "author", None)) if meta else None
    if not title:
        title = _title_from_filename(path)

    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text.strip())

    return ExtractedPdf(
        title=title,
        author=author,
        num_pages=len(pages),
        pages=pages,
    )
