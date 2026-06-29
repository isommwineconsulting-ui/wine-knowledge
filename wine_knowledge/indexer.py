"""Persist extracted PDFs into Supabase: catalog row + per-page text rows."""

from __future__ import annotations

from datetime import datetime, timezone

from .config import get_supabase
from .extractor import ExtractedPdf

# Lightweight keyword tagging so the catalog is browsable by topic.
_TOPIC_KEYWORDS = {
    "burgundy", "bordeaux", "champagne", "rioja", "tuscany", "napa",
    "pinot noir", "cabernet", "chardonnay", "riesling", "syrah", "merlot",
    "tannin", "terroir", "vintage", "fermentation", "viticulture",
    "sommelier", "tasting", "pairing", "sparkling", "rose",
}


def document_exists(sha256: str) -> str | None:
    """Return the document id if a PDF with this hash is already indexed."""
    client = get_supabase()
    resp = (
        client.table("pdf_documents")
        .select("id")
        .eq("file_sha256", sha256)
        .limit(1)
        .execute()
    )
    if resp.data:
        return resp.data[0]["id"]
    return None


def _derive_tags(extracted: ExtractedPdf, sample_pages: int = 5) -> list[str]:
    sample = " ".join(extracted.pages[:sample_pages]).lower()
    return sorted({kw for kw in _TOPIC_KEYWORDS if kw in sample})


def index_document(
    *,
    extracted: ExtractedPdf,
    pdf_url: str,
    source_page_url: str,
    storage_path: str,
    sha256: str,
    size_bytes: int,
) -> str:
    """Insert the document and its pages. Returns the new document id."""
    client = get_supabase()

    doc_payload = {
        "title": extracted.title,
        "author": extracted.author,
        "source_page_url": source_page_url,
        "pdf_url": pdf_url,
        "storage_path": storage_path,
        "file_sha256": sha256,
        "file_size_bytes": size_bytes,
        "num_pages": extracted.num_pages,
        "topic_tags": _derive_tags(extracted),
        "status": "indexed",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    doc_resp = client.table("pdf_documents").insert(doc_payload).execute()
    document_id = doc_resp.data[0]["id"]

    page_rows = [
        {
            "document_id": document_id,
            "page_number": i + 1,
            "content": text,
        }
        for i, text in enumerate(extracted.pages)
        if text  # skip empty/image-only pages
    ]

    # Insert pages in batches to stay well under request size limits.
    batch_size = 50
    for start in range(0, len(page_rows), batch_size):
        client.table("pdf_pages").insert(page_rows[start : start + batch_size]).execute()

    return document_id
