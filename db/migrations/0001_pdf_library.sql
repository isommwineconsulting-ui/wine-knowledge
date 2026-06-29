-- Wine PDF library: catalog + full-text searchable page index.
-- Additive to the existing schema; all objects are prefixed pdf_*.

create extension if not exists unaccent;

-- ---------------------------------------------------------------------------
-- Catalog: one row per ingested PDF.
-- ---------------------------------------------------------------------------
create table if not exists public.pdf_documents (
    id              uuid primary key default gen_random_uuid(),
    title           text,
    author          text,
    source_page_url text,
    pdf_url         text not null,
    storage_path    text,
    file_sha256     text not null unique,
    file_size_bytes bigint,
    num_pages       integer,
    topic_tags      text[] not null default '{}',
    status          text not null default 'indexed',
    scraped_at      timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists pdf_documents_title_trgm
    on public.pdf_documents using gin (title gin_trgm_ops);
create index if not exists pdf_documents_tags
    on public.pdf_documents using gin (topic_tags);

-- ---------------------------------------------------------------------------
-- Full text: one row per page, with a generated tsvector for search.
-- ---------------------------------------------------------------------------
create table if not exists public.pdf_pages (
    id          uuid primary key default gen_random_uuid(),
    document_id uuid not null references public.pdf_documents(id) on delete cascade,
    page_number integer not null,
    content     text not null,
    content_tsv tsvector generated always as (
        to_tsvector('english', coalesce(content, ''))
    ) stored,
    embedding   vector(1536),
    created_at  timestamptz not null default now(),
    unique (document_id, page_number)
);

create index if not exists pdf_pages_tsv
    on public.pdf_pages using gin (content_tsv);
create index if not exists pdf_pages_document
    on public.pdf_pages (document_id);

-- ---------------------------------------------------------------------------
-- updated_at maintenance for pdf_documents.
-- ---------------------------------------------------------------------------
create or replace function public.pdf_set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists pdf_documents_set_updated_at on public.pdf_documents;
create trigger pdf_documents_set_updated_at
    before update on public.pdf_documents
    for each row execute function public.pdf_set_updated_at();

-- ---------------------------------------------------------------------------
-- Search RPC: rank pages, return a document-aware snippet.
-- SECURITY DEFINER so the app can search regardless of row ownership.
-- ---------------------------------------------------------------------------
create or replace function public.search_pdf_library(query text, max_results integer default 10)
returns table (
    document_id uuid,
    title       text,
    author      text,
    page_number integer,
    snippet     text,
    rank        real
)
language sql
stable
security definer
set search_path = public
as $$
    select
        d.id as document_id,
        d.title,
        d.author,
        p.page_number,
        ts_headline(
            'english',
            p.content,
            websearch_to_tsquery('english', query),
            'StartSel=**, StopSel=**, MaxFragments=2, MinWords=5, MaxWords=20'
        ) as snippet,
        ts_rank(p.content_tsv, websearch_to_tsquery('english', query)) as rank
    from public.pdf_pages p
    join public.pdf_documents d on d.id = p.document_id
    where p.content_tsv @@ websearch_to_tsquery('english', query)
    order by rank desc
    limit greatest(max_results, 1);
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security: read for authenticated users; writes via service role
-- (which bypasses RLS). Search RPC is exposed to anon + authenticated.
-- ---------------------------------------------------------------------------
alter table public.pdf_documents enable row level security;
alter table public.pdf_pages enable row level security;

drop policy if exists pdf_documents_read on public.pdf_documents;
create policy pdf_documents_read
    on public.pdf_documents for select
    to authenticated
    using (true);

drop policy if exists pdf_pages_read on public.pdf_pages;
create policy pdf_pages_read
    on public.pdf_pages for select
    to authenticated
    using (true);

grant execute on function public.search_pdf_library(text, integer) to anon, authenticated;

-- ---------------------------------------------------------------------------
-- Private storage bucket for the PDF files.
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('wine-pdfs', 'wine-pdfs', false)
on conflict (id) do nothing;
