-- Required by 0001_pdf_library.sql.
-- Candidate prerequisite; execute in controlled staging before 0001.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
