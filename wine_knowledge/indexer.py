"""Persist extracted PDFs into Supabase: catalog row + per-page text rows."""

from __future__ import annotations


from .config import get_supabase, get_settings
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
    storage_path: str | None,
    sha256: str,
    size_bytes: int,
) -> str:
    """Insert the document and its pages. Returns the new document id."""
    client = get_supabase()
    owner_id = get_settings().owner_id

    if len(sha256) != 64 or not extracted.pages:
        raise ValueError("Invalid digest or empty document")

    # The database function validates ownership, locks the SHA-256 key, and
    # commits catalog + page records in a single Postgres transaction.
    # Never mark a document indexed on the client before pages are durable.
    result = client.rpc(
        "ingest_pdf_document",
        {
            "p_owner_id": owner_id,
            "p_title": extracted.title,
            "p_author": extracted.author,
            "p_source_page_url": source_page_url,
            "p_pdf_url": pdf_url,
            "p_storage_path": storage_path,
            "p_sha256": sha256,
            "p_file_size_bytes": size_bytes,
            "p_pages": extracted.pages,
            "p_topic_tags": _derive_tags(extracted),
        },
    ).execute()
    if not result.data:
        raise RuntimeError("Ingestion RPC did not return a document ID")
    return str(result.data)
