"""Command-line interface for wine-knowledge."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .config import ConfigError

app = typer.Typer(
    add_completion=False,
    help="Scrape wine PDFs into a searchable master reference index.",
)


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


@app.command()
def scrape(
    url: str = typer.Argument(..., help="Seed URL to scan for PDF links."),
    crawl_depth: int = typer.Option(
        0, "--crawl-depth", "-d", help="Follow same-domain links to this depth."
    ),
    max_pdfs: Optional[int] = typer.Option(
        None, "--max-pdfs", "-n", help="Stop after this many PDFs."
    ),
    dest_dir: Optional[Path] = typer.Option(
        None, "--dest-dir", help="Keep downloads here instead of a temp dir."
    ),
) -> None:
    """Scrape a page for wine PDFs, store them, and index their text."""
    from .pipeline import scrape_and_ingest

    def on_links(links) -> None:
        typer.secho(f"Found {len(links)} PDF link(s).", fg=typer.colors.CYAN)

    def on_result(result) -> None:
        color = {
            "indexed": typer.colors.GREEN,
            "skipped": typer.colors.YELLOW,
            "error": typer.colors.RED,
        }.get(result.status, typer.colors.WHITE)
        typer.secho(
            f"  [{result.status:>7}] {result.pdf_url}  {result.detail}", fg=color
        )

    try:
        results = scrape_and_ingest(
            url,
            crawl_depth=crawl_depth,
            max_pdfs=max_pdfs,
            dest_dir=dest_dir,
            on_link_found=on_links,
            on_result=on_result,
        )
    except ConfigError as exc:
        _fail(str(exc))
        return

    indexed = sum(1 for r in results if r.status == "indexed")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = sum(1 for r in results if r.status == "error")
    typer.secho(
        f"\nDone: {indexed} indexed, {skipped} skipped, {errors} error(s).",
        fg=typer.colors.CYAN,
        bold=True,
    )


@app.command()
def ingest(
    path: Path = typer.Argument(
        ..., exists=True, help="A PDF file or a folder of PDFs to index."
    ),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Recurse into subfolders."
    ),
    upload: bool = typer.Option(
        True,
        "--upload/--no-upload",
        help="Copy files into Supabase Storage (off = index in place).",
    ),
) -> None:
    """Index wine PDFs you already have on disk — no scraping required."""
    from .pipeline import ingest_local

    def on_result(result) -> None:
        color = {
            "indexed": typer.colors.GREEN,
            "skipped": typer.colors.YELLOW,
            "error": typer.colors.RED,
        }.get(result.status, typer.colors.WHITE)
        typer.secho(f"  [{result.status:>7}] {result.pdf_url}  {result.detail}", fg=color)

    try:
        results = ingest_local(
            path, recursive=recursive, upload=upload, on_result=on_result
        )
    except ConfigError as exc:
        _fail(str(exc))
        return

    if not results:
        typer.secho("No PDF files found.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    indexed = sum(1 for r in results if r.status == "indexed")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = sum(1 for r in results if r.status == "error")
    typer.secho(
        f"\nDone: {indexed} indexed, {skipped} skipped, {errors} error(s).",
        fg=typer.colors.CYAN,
        bold=True,
    )


@app.command()
def search(
    query: str = typer.Argument(..., help="Full-text query."),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results."),
) -> None:
    """Search the indexed library and print ranked snippets."""
    from .search import search as run_search

    try:
        hits = run_search(query, limit=limit)
    except ConfigError as exc:
        _fail(str(exc))
        return

    if not hits:
        typer.secho("No matches.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    for hit in hits:
        title = hit.title or "(untitled)"
        author = f" — {hit.author}" if hit.author else ""
        typer.secho(f"\n{title}{author}  (p.{hit.page_number})", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"  {hit.snippet}")


@app.command(name="list")
def list_documents(
    limit: int = typer.Option(50, "--limit", "-l", help="Max rows."),
) -> None:
    """List catalogued documents."""
    from .config import get_supabase

    try:
        client = get_supabase()
    except ConfigError as exc:
        _fail(str(exc))
        return

    resp = (
        client.table("pdf_documents")
        .select("title, author, num_pages, topic_tags, source_page_url")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        typer.secho("Library is empty.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    for row in rows:
        title = row.get("title") or "(untitled)"
        author = f" — {row['author']}" if row.get("author") else ""
        tags = ", ".join(row.get("topic_tags") or [])
        typer.secho(f"{title}{author}", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"  {row.get('num_pages', 0)} pages | {tags}")


@app.command()
def stats() -> None:
    """Show library counts."""
    from .config import get_supabase

    try:
        client = get_supabase()
    except ConfigError as exc:
        _fail(str(exc))
        return

    docs = client.table("pdf_documents").select("id", count="exact").execute()
    pages = client.table("pdf_pages").select("id", count="exact").execute()
    typer.secho(
        f"Documents: {docs.count or 0}\nPages indexed: {pages.count or 0}",
        fg=typer.colors.CYAN,
    )


if __name__ == "__main__":
    app()
