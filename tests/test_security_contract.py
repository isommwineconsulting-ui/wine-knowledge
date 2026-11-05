"""Static fail-closed regression checks; live Postgres tests remain mandatory."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "db/migrations/0002_scoped_atomic_ingestion.sql").read_text().lower()
INDEXER = (ROOT / "wine_knowledge/indexer.py").read_text()
PIPELINE = (ROOT / "wine_knowledge/pipeline.py").read_text()
CONFIG = (ROOT / "wine_knowledge/config.py").read_text()


def test_replaces_privileged_anonymous_search() -> None:
    assert "security invoker" in MIGRATION
    assert "from public, anon, authenticated" in MIGRATION
    assert "grant execute on function public.search_pdf_library" in MIGRATION
    assert "to authenticated" in MIGRATION
    assert "d.owner_id = auth.uid()" in MIGRATION


def test_legacy_records_quarantined() -> None:
    assert "owner_id = (select auth.uid())" in MIGRATION
    assert "check (owner_id is not null) not valid" in MIGRATION


def test_atomic_ingest_and_privilege() -> None:
    assert "pg_advisory_xact_lock" in MIGRATION
    assert "status = 'indexed'" in MIGRATION
    assert "get diagnostics v_count = row_count" in MIGRATION
    assert "service role required" in MIGRATION
    assert 'client.rpc(\n        "ingest_pdf_document"' in INDEXER
    assert "client.table(\"pdf_documents\").insert(" not in INDEXER
    assert "indexer.document_exists(" not in PIPELINE


def test_owner_configuration_fail_closed() -> None:
    assert 'WINE_PDF_OWNER_ID' in CONFIG
    assert 'uuid.UUID(owner_id)' in CONFIG
