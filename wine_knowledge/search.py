"""Full-text search over the indexed PDF library via the Supabase RPC."""

from __future__ import annotations

from dataclasses import dataclass

from .config import get_supabase


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    title: str | None
    author: str | None
    page_number: int
    snippet: str
    rank: float


def search(query: str, limit: int = 10) -> list[SearchHit]:
    """Run a full-text query against search_pdf_library and return ranked hits."""
    client = get_supabase()
    resp = client.rpc(
        "search_pdf_library",
        {"query": query, "max_results": limit},
    ).execute()

    hits: list[SearchHit] = []
    for row in resp.data or []:
        hits.append(
            SearchHit(
                document_id=row["document_id"],
                title=row.get("title"),
                author=row.get("author"),
                page_number=row["page_number"],
                snippet=row.get("snippet", ""),
                rank=row.get("rank", 0.0),
            )
        )
    return hits
