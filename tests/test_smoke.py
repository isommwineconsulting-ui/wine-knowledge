"""Offline smoke tests: PDF extraction, link parsing, and tagging.

These exercise the pure pipeline pieces without needing a live site or
Supabase credentials.
"""

from __future__ import annotations

from pathlib import Path

from wine_knowledge.downloader import filename_from_url, inspect_local
from wine_knowledge.extractor import extract
from wine_knowledge.pipeline import find_local_pdfs
from wine_knowledge.indexer import _derive_tags
from wine_knowledge.extractor import ExtractedPdf
from wine_knowledge.scraper import parse_links
from wine_knowledge.storage import storage_path_for


def _build_minimal_pdf(text: str) -> bytes:
    """Build a tiny single-page PDF with a correct xref table."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\nBT /F1 24 Tf 72 700 Td (%s) Tj ET\nendstream"
        % (len(text) + 26, text.encode("latin-1")),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + body + b"\nendobj\n"

    xref_pos = len(pdf)
    pdf += b"xref\n0 %d\n" % (len(objects) + 1)
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += (
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"
        % (len(objects) + 1, xref_pos)
    )
    return bytes(pdf)


def test_extract_reads_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "Bordeaux Tannin Terroir.pdf"
    pdf_path.write_bytes(_build_minimal_pdf("Bordeaux tannin terroir"))

    result = extract(pdf_path)

    assert result.num_pages == 1
    assert "tannin" in result.pages[0].lower()
    # No metadata title -> falls back to a cleaned filename.
    assert result.title == "Bordeaux Tannin Terroir"


def test_parse_links_finds_pdfs_and_pages() -> None:
    html = """
    <html><body>
      <a href="books/intro-to-wine.pdf">Intro to Wine</a>
      <a href="/papers/terroir.PDF">Terroir paper</a>
      <a href="more-books.html">More books</a>
      <a href="https://other.com/x.pdf">External</a>
    </body></html>
    """
    pdfs, others = parse_links(html, "https://example.com/library/")

    pdf_urls = {p.pdf_url for p in pdfs}
    assert "https://example.com/library/books/intro-to-wine.pdf" in pdf_urls
    assert "https://example.com/papers/terroir.PDF" in pdf_urls
    assert "https://other.com/x.pdf" in pdf_urls
    assert "https://example.com/library/more-books.html" in others


def test_derive_tags_picks_keywords() -> None:
    extracted = ExtractedPdf(
        title="t",
        author=None,
        num_pages=1,
        pages=["A study of Bordeaux terroir and tannin in vintage wines."],
    )
    tags = _derive_tags(extracted)
    assert "bordeaux" in tags
    assert "terroir" in tags
    assert "tannin" in tags


def test_inspect_local_and_find_pdfs(tmp_path: Path) -> None:
    pdf = tmp_path / "sub" / "Burgundy Notes.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(_build_minimal_pdf("Burgundy pinot noir"))
    (tmp_path / "notes.txt").write_text("not a pdf")

    info = inspect_local(pdf)
    assert info.filename == "Burgundy Notes.pdf"
    assert len(info.sha256) == 64
    assert info.size_bytes == pdf.stat().st_size

    # Directory walk finds only the PDF, recursively.
    found = find_local_pdfs(tmp_path, recursive=True)
    assert found == [pdf]
    assert find_local_pdfs(tmp_path, recursive=False) == []


def test_inspect_local_rejects_non_pdf(tmp_path: Path) -> None:
    import pytest

    bad = tmp_path / "fake.pdf"
    bad.write_bytes(b"not really a pdf")
    with pytest.raises(ValueError):
        inspect_local(bad)


def test_storage_path_and_filename() -> None:
    sha = "abcd1234" + "0" * 56
    assert storage_path_for(sha, "book.pdf") == f"ab/{sha}/book.pdf"
    assert filename_from_url("https://x.com/a/b/Wine%20Guide.pdf") == "Wine Guide.pdf"
