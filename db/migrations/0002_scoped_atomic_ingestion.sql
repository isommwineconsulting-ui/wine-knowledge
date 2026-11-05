-- CANDIDATE: fail-closed ownership and atomic PDF ingestion.
-- Apply only after reviewing the existing schema and backing up the database.
-- Historical records without owner_id remain quarantined from client reads.
BEGIN;

ALTER TABLE public.pdf_documents
  ADD COLUMN IF NOT EXISTS owner_id uuid;

CREATE INDEX IF NOT EXISTS pdf_documents_owner_idx
  ON public.pdf_documents(owner_id);

ALTER TABLE public.pdf_documents
  DROP CONSTRAINT IF EXISTS pdf_documents_owner_required;
ALTER TABLE public.pdf_documents
  ADD CONSTRAINT pdf_documents_owner_required CHECK (owner_id IS NOT NULL) NOT VALID;

DROP POLICY IF EXISTS pdf_documents_read ON public.pdf_documents;
DROP POLICY IF EXISTS pdf_pages_read ON public.pdf_pages;
DROP POLICY IF EXISTS pdf_documents_owner_read ON public.pdf_documents;
DROP POLICY IF EXISTS pdf_pages_owner_read ON public.pdf_pages;

CREATE POLICY pdf_documents_owner_read ON public.pdf_documents
  FOR SELECT TO authenticated
  USING (owner_id = (select auth.uid()) AND status = 'indexed');

CREATE POLICY pdf_pages_owner_read ON public.pdf_pages
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.pdf_documents d
    WHERE d.id = document_id AND d.owner_id = (select auth.uid())
      AND d.status = 'indexed'
  ));

-- Do not rely on the definer's privileges to bypass document ownership.
CREATE OR REPLACE FUNCTION public.search_pdf_library(query text, max_results integer DEFAULT 10)
RETURNS TABLE (
    document_id uuid, title text, author text,
    page_number integer, snippet text, rank real
)
LANGUAGE sql STABLE SECURITY INVOKER
SET search_path = pg_catalog, public
AS $fn$
  SELECT d.id, d.title, d.author, p.page_number,
    ts_headline('english', p.content, websearch_to_tsquery('english', query),
      'StartSel=**, StopSel=**, MaxFragments=2, MinWords=5, MaxWords=20'),
    ts_rank(p.content_tsv, websearch_to_tsquery('english', query))
  FROM public.pdf_pages p
  JOIN public.pdf_documents d ON d.id = p.document_id
  WHERE d.owner_id = auth.uid() AND d.status = 'indexed'
    AND p.content_tsv @@ websearch_to_tsquery('english', query)
  ORDER BY 6 DESC
  LIMIT LEAST(GREATEST(max_results, 1), 100);
$fn$;

REVOKE ALL ON FUNCTION public.search_pdf_library(text, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_pdf_library(text, integer)
  TO authenticated, service_role;
GRANT SELECT ON public.pdf_documents, public.pdf_pages TO authenticated;

-- One RPC call = one DB transaction; all derived page rows and catalog state
-- commit together or roll back together. No partial INDEXED result.
CREATE OR REPLACE FUNCTION public.ingest_pdf_document(
  p_owner_id uuid,
  p_title text,
  p_author text,
  p_source_page_url text,
  p_pdf_url text,
  p_storage_path text,
  p_sha256 text,
  p_file_size_bytes bigint,
  p_pages text[]
)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
  v_id uuid;
  v_existing public.pdf_documents%ROWTYPE;
  v_count integer;
  v_expected integer;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role'
  THEN
    RAISE EXCEPTION 'service role required' USING ERRCODE = '42501';
  END IF;
  IF p_owner_id IS NULL OR p_sha256 !~ '^[a-f0-9]{64}$'
     OR p_file_size_bytes < 5 OR p_pages IS NULL
     OR cardinality(p_pages) = 0 OR p_pdf_url IS NULL
  THEN
    RAISE EXCEPTION 'invalid ingestion input' USING ERRCODE = '22023';
  END IF;
  -- Require a real authenticated owner, not merely any well-formed UUID.
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = p_owner_id) THEN
    RAISE EXCEPTION 'unknown owner' USING ERRCODE = '22023';
  END IF;
  -- Require extractable text; otherwise record requires separate review.
  SELECT count(*) INTO v_expected FROM unnest(p_pages) AS u(page_text)
    WHERE page_text IS NOT NULL AND btrim(page_text) <> '';
  IF v_expected = 0 THEN
    RAISE EXCEPTION 'no extractable text' USING ERRCODE = '22023';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_sha256, 0));
  SELECT * INTO v_existing FROM public.pdf_documents
    WHERE file_sha256 = p_sha256 FOR UPDATE;
  IF FOUND THEN
    IF v_existing.owner_id IS DISTINCT FROM p_owner_id
       OR v_existing.status <> 'indexed'
       OR v_existing.num_pages <> cardinality(p_pages)
       OR (SELECT count(*) FROM public.pdf_pages WHERE document_id = v_existing.id) <> v_expected
    THEN
      RAISE EXCEPTION 'hash collision, unowned legacy row or incomplete index: manual reconciliation required'
        USING ERRCODE = '23505';
    END IF;
    RETURN v_existing.id;
  END IF;

  INSERT INTO public.pdf_documents
    (owner_id, title, author, source_page_url, pdf_url, storage_path,
     file_sha256, file_size_bytes, num_pages, status, scraped_at)
  VALUES
    (p_owner_id, p_title, p_author, p_source_page_url, p_pdf_url,
     p_storage_path, p_sha256, p_file_size_bytes, cardinality(p_pages),
     'indexing', now())
  RETURNING id INTO v_id;

  INSERT INTO public.pdf_pages(document_id, page_number, content)
  SELECT v_id, ordinality::integer, page_text
  FROM unnest(p_pages) WITH ORDINALITY AS u(page_text, ordinality)
  WHERE page_text IS NOT NULL AND btrim(page_text) <> '';

  GET DIAGNOSTICS v_count = ROW_COUNT;
  IF v_count <> v_expected THEN
    RAISE EXCEPTION 'incomplete page insert' USING ERRCODE = '23514';
  END IF;
  UPDATE public.pdf_documents SET status = 'indexed' WHERE id = v_id;
  RETURN v_id;
END;
$fn$;

REVOKE ALL ON FUNCTION public.ingest_pdf_document(uuid,text,text,text,text,text,text,bigint,text[])
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ingest_pdf_document(uuid,text,text,text,text,text,text,bigint,text[])
  TO service_role;
COMMIT;
