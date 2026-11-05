# CANDIDATE remediation: release authority INACTIVE

This branch is experimental. The project's canonical GitHub membership is not established.
Do **not** apply migrations to an unreviewed production database.

## Preconditions
1. Confirm GitHub/project identity, take a restorable database backup and capture migration history.
2. Apply `0000_extensions.sql` before `0001_pdf_library.sql` on a new database.
3. Apply `0002_scoped_atomic_ingestion.sql` only after reviewing existing policies and function owners.
4. Assign a verified user UUID to `WINE_PDF_OWNER_ID`; never use a made-up owner.
5. Unowned historical rows remain invisible to authenticated searches until individually reconciled.

## Mandatory runtime verification
- anonymous search is denied; authenticated user cannot read another owner's document.
- service-role atomic insert commits full catalog+pages or zero catalog+pages under forced failure.
- retry under same SHA returns one ID without duplicating pages, including concurrency.
- malformed hash, empty text, missing owner, and incomplete legacy document fail closed.
- Storage orphan reconciliation and secrets handling are independently checked.
- Re-check active database migrations, grants, storage policies, and CI branch protection.
- Obtain source-level producer citations and independent factual review.
- Obtain separate human release authorization and signed hash manifest.

No runtime, production, or release approval is implied by this candidate branch.
