"""End-to-end ingest: scrape -> download -> store -> extract -> index."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import downloader, extractor, indexer, storage
from .scraper import PdfLink, Scraper


@dataclass
class IngestResult:
    pdf_url: str
    status: str  # "indexed" | "skipped" | "error"
    detail: str = ""
    document_id: str | None = None


def ingest_pdf(link: PdfLink, dest_dir: Path) -> IngestResult:
    """Ingest a single PDF link. Idempotent: skips already-indexed hashes."""
    try:
        downloaded = downloader.download(link.pdf_url, dest_dir)
    except Exception as exc:  # network error, not-a-pdf, etc.
        return IngestResult(link.pdf_url, "error", f"download failed: {exc}")

    try:
        extracted = extractor.extract(downloaded.path)
    except Exception as exc:
        return IngestResult(link.pdf_url, "error", f"extract failed: {exc}")

    try:
        object_path = storage.upload_pdf(
            downloaded.path, downloaded.sha256, downloaded.filename
        )
    except Exception as exc:
        return IngestResult(link.pdf_url, "error", f"upload failed: {exc}")

    try:
        document_id = indexer.index_document(
            extracted=extracted,
            pdf_url=link.pdf_url,
            source_page_url=link.source_page_url,
            storage_path=object_path,
            sha256=downloaded.sha256,
            size_bytes=downloaded.size_bytes,
        )
    except Exception as exc:
        return IngestResult(link.pdf_url, "error", f"index failed: {exc}")

    return IngestResult(
        link.pdf_url,
        "indexed",
        f"{extracted.num_pages} pages",
        document_id=document_id,
    )


def ingest_local_file(path: Path, *, upload: bool = True) -> IngestResult:
    """Ingest a PDF already on disk. Idempotent via SHA-256 dedupe.

    When ``upload`` is False the file is indexed in place without copying it to
    Supabase Storage (storage_path stays null); useful for large local libraries.
    """
    label = str(path)
    try:
        info = downloader.inspect_local(path)
    except Exception as exc:
        return IngestResult(label, "error", f"read failed: {exc}")

    try:
        extracted = extractor.extract(path)
    except Exception as exc:
        return IngestResult(label, "error", f"extract failed: {exc}")

    object_path = None
    if upload:
        try:
            object_path = storage.upload_pdf(path, info.sha256, info.filename)
        except Exception as exc:
            return IngestResult(label, "error", f"upload failed: {exc}")

    try:
        document_id = indexer.index_document(
            extracted=extracted,
            pdf_url=path.resolve().as_uri(),
            source_page_url="local-ingest",
            storage_path=object_path,
            sha256=info.sha256,
            size_bytes=info.size_bytes,
        )
    except Exception as exc:
        return IngestResult(label, "error", f"index failed: {exc}")

    return IngestResult(
        label, "indexed", f"{extracted.num_pages} pages", document_id=document_id
    )


def find_local_pdfs(target: Path, recursive: bool = True) -> list[Path]:
    """Return PDF files under ``target`` (a file or directory)."""
    if target.is_file():
        return [target] if target.suffix.lower() == ".pdf" else []
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in target.glob(pattern) if p.is_file())


def ingest_local(
    target: Path,
    *,
    recursive: bool = True,
    upload: bool = True,
    on_result: Callable[[IngestResult], None] | None = None,
) -> list[IngestResult]:
    """Ingest a local PDF file or every PDF in a directory."""
    results: list[IngestResult] = []
    for pdf_path in find_local_pdfs(target, recursive=recursive):
        result = ingest_local_file(pdf_path, upload=upload)
        results.append(result)
        if on_result:
            on_result(result)
    return results


def scrape_and_ingest(
    seed_url: str,
    *,
    crawl_depth: int = 0,
    max_pdfs: int | None = None,
    dest_dir: Path | None = None,
    on_link_found: Callable[[list[PdfLink]], None] | None = None,
    on_result: Callable[[IngestResult], None] | None = None,
) -> list[IngestResult]:
    """Find PDFs from ``seed_url`` and ingest them. Returns per-PDF results."""
    with Scraper() as scraper:
        links = scraper.find_pdfs(seed_url, crawl_depth=crawl_depth)

    if max_pdfs is not None:
        links = links[:max_pdfs]
    if on_link_found:
        on_link_found(links)

    results: list[IngestResult] = []
    cleanup = dest_dir is None
    work_dir = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix="wine-pdf-"))
    try:
        for link in links:
            result = ingest_pdf(link, work_dir)
            results.append(result)
            if on_result:
                on_result(result)
    finally:
        if cleanup:
            import shutil

            shutil.rmtree(work_dir, ignore_errors=True)
    return results
