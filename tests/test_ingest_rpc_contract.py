"""Unit-level contract of the Python to atomic-RPC boundary."""
from types import SimpleNamespace

from wine_knowledge.extractor import ExtractedPdf
from wine_knowledge import indexer


class _Client:
    def __init__(self):
        self.calls = []

    def rpc(self, method, payload):
        self.calls.append((method, payload))
        return self

    def execute(self):
        return SimpleNamespace(data="11111111-1111-4111-8111-111111111111")


def test_indexing_routes_pages_and_tags_through_one_rpc(monkeypatch):
    client = _Client()
    monkeypatch.setattr(indexer, "get_supabase", lambda: client)
    monkeypatch.setattr(indexer, "get_settings", lambda: SimpleNamespace(
        owner_id="22222222-2222-4222-8222-222222222222"))
    extracted = ExtractedPdf(
        title="Demo", author=None, num_pages=2,
        pages=["Bordeaux tannin", ""]
    )
    document_id = indexer.index_document(
        extracted=extracted, pdf_url="file:///demo.pdf",
        source_page_url="local-ingest", storage_path=None,
        sha256="a" * 64, size_bytes=250
    )
    assert document_id == "11111111-1111-4111-8111-111111111111"
    assert len(client.calls) == 1
    name, payload = client.calls[0]
    assert name == "ingest_pdf_document"
    assert payload["p_owner_id"] == "22222222-2222-4222-8222-222222222222"
    assert payload["p_pages"] == ["Bordeaux tannin", ""]
    assert payload["p_topic_tags"] == ["bordeaux", "tannin"]
    assert payload["p_storage_path"] is None
