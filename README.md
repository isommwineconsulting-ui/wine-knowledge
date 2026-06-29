# wine-knowledge

Scrape a website for wine-related PDF books, store them, and build a **master
reference index** with full-text search — backed by Supabase
(Postgres + Storage).

## What it does

1. **Scrape** — given a URL, find PDF links (optionally crawling same-domain
   pages to a depth you choose). Polite by default: identifies itself, honours
   `robots.txt`, and rate-limits.
2. **Download & dedupe** — stream each PDF, verify it really is a PDF, and skip
   anything already indexed (matched by SHA-256).
3. **Store** — upload the file to a private Supabase Storage bucket (`wine-pdfs`).
4. **Extract & index** — pull per-page text and metadata (title/author) with
   `pypdf`, and write a catalog row plus one searchable row per page.
5. **Search** — full-text query across the whole library, returning ranked
   snippets with the document and page they came from.

## Data model

Applied by `db/migrations/0001_pdf_library.sql`:

- **`pdf_documents`** — the catalog (title, author, source URL, storage path,
  SHA-256, page count, topic tags, status, timestamps).
- **`pdf_pages`** — one row per page with a generated `tsvector` (GIN-indexed)
  for full-text search, plus a nullable `embedding vector(1536)` reserved for
  future semantic search (pgvector is already installed).
- **`search_pdf_library(query, max_results)`** — ranked search RPC returning
  `ts_headline` snippets.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: set SUPABASE_SERVICE_ROLE_KEY (Project Settings -> API)
```

Apply the migration once (via the Supabase dashboard SQL editor, the Supabase
CLI, or an MCP `apply_migration` call) using `db/migrations/0001_pdf_library.sql`.

## Usage

```bash
# Scrape one page for PDFs and index them
python -m wine_knowledge scrape "https://example.com/wine-library"

# Crawl same-domain links two levels deep, cap at 20 PDFs
python -m wine_knowledge scrape "https://example.com/library" --crawl-depth 2 --max-pdfs 20

# Full-text search the index
python -m wine_knowledge search "tannin structure in aged Bordeaux"

# Browse / count
python -m wine_knowledge list
python -m wine_knowledge stats
```

## Configuration (`.env`)

| Variable | Required | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | yes | Project URL, e.g. `https://umbmsiqplmigddbhzima.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Service-role key — needed for writes. Keep secret. |
| `WINE_PDF_BUCKET` | no | Storage bucket name (default `wine-pdfs`). |
| `WINE_SCRAPER_USER_AGENT` | no | User-Agent the scraper sends. |
| `WINE_SCRAPER_DELAY_SECONDS` | no | Delay between page fetches (default `1.0`). |

## Future: semantic search

The `pdf_pages.embedding` column and pgvector are in place. To enable semantic
search, generate embeddings for each page's `content`, store them in
`embedding`, add an HNSW index, and extend `search_pdf_library` (or add a new
RPC) to combine vector similarity with the existing full-text rank.

## Responsible use

You are responsible for the legality of the sources you point this at. Use it
only on content you are permitted to download and store (public-domain or
licensed wine material).
