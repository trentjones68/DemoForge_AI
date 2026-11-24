# Manual discovery ingestion

Open an opportunity and choose **Discovery sessions**. Create a session with a
title and optional meeting date. Paste a transcript or upload a TXT, Markdown,
DOCX, or PDF with selectable text. Choose **Plaud export** for files exported
manually from Plaud. Import an optional summary separately with **Summary**
selected. Every import requires consent attestation. The viewer renders source
text literally, shows provenance and recognized speaker and time markers, and
provides a permalink to each segment and a private original download.

Workspace admins can create sessions and import sources on active opportunities.
Sales engineers can import on opportunities they own. Admins and sales engineers
can read discovery records in their own workspace. Archived opportunities allow
reads. Viewer and product admin roles have no discovery text or original access.

## Setup and validation

1. Start disposable local Supabase and set up the separate migration and request
   database logins and JWT verifier per [Identity](IDENTITY.md).
2. Provision the [analysis worker login](ANALYSIS.md#provision-the-worker) for
   a migration to head, or run `make migrate REVISION=0005` for the ingestion
   schema alone. Revision `0005` requires Supabase
   Storage and adds `discovery-originals`, a private bucket with a restrictive
   policy that blocks direct browser access. Bare Compose remains at `0002`.
3. In server-only API settings, set `SUPABASE_STORAGE_URL` to the trusted
   project Storage endpoint, such as `http://127.0.0.1:54321/storage/v1`
   locally. Set `SUPABASE_STORAGE_SERVICE_KEY` to the same project's
   server-only secret key or local service-role JWT. The application confines
   use of this credential to original writes and signing in the discovery
   bucket. Hosted installations use HTTPS. Keep the key out of web settings
   and browser bundles. Use a Linux API runtime for the parser resource limits.
4. Run the API and web per the README. Use only synthetic content for
   development and review. Start at an opportunity and verify the empty
   view, form keyboard navigation, paste upload, optional summary, and
   the segment permalink. A second import of the same bytes and source type
   should show the existing source. Try an image-only PDF for the actionable
   error and verify a downloaded original matches the input bytes.

`make check` covers parser validation. The
[Supabase test runner](../tests/run_local_supabase.py) takes a status JSON from a
fresh disposable instance. It verifies real Auth, private Storage, direct
cross-tenant IDs and RLS, retry after a lost Storage response, and migration
upgrade and downgrade. Keep the status JSON in a temporary file with mode 0600
because the local CLI includes credentials.

## Limits and recovery

- Each original is limited to 2 MiB. Each extracted source allows 250,000
  Unicode code points and 3,000 segments. A PDF may have up to 60 pages. DOCX
  is limited to 128 ZIP entries, 8 MiB declared expanded size, and 4 MiB of
  document XML. The subprocess has a five-second wall limit and CPU and memory
  limits. It runs with a sanitized environment and blocks Python network
  and external file access. It does not open ZIP entries as filesystem paths,
  fetch embedded links, or execute document content. A PDF with no text layer
  must be OCRed by the user or exported in another format.
- A session accepts up to 20 sources, a workspace up to 200 sources and
  100 MiB of originals, and an opportunity up to 50 sessions. Concurrent
  request bodies and parser processes are bounded per API instance.
- SHA-256 deduplication is scoped to workspace, session, and source type.
  The first import keeps its provenance. A summary is independent of the
  transcript even when its bytes match. Segment IDs are derived from the
  immutable source ID and ordinal. Offsets are zero-based Unicode code points
  with exclusive end positions in the full extracted text with LF line endings.
- Validation precedes the first Storage request. The API commits a pending
  reservation, writes the original under its generated path, and atomically
  publishes segments and an import audit event. Re-submit the same bytes in
  the same session and source type if a Storage write or completion is
  interrupted. Pending reservations count toward quota and are omitted from
  the viewer. Originals use 60-second signed attachment URLs. Anyone holding a
  link may use it until it expires, including after membership revocation.
- The import runs as a bounded request, with durable reservations for the
  Storage boundary. The durable background queue, worker-driven parsing and
  automated Plaud handoff are separate work. The Plaud adapter represents a
  manual export; there is no verified direct sync in this milestone.
- Before production ingestion, resolve consent wording, retention and deletion,
  data residency, parser isolation and malware scanning with privacy and
  security owners. Set authenticated rate and request-size limits at ingress.
  Originals are provided as attachments and may contain active content when
  opened in external applications.

## Rollback

Stop discovery traffic and back up the revision `0005` tables and private
originals together. Confirm the restore plan before removing records. Empty and
delete the `discovery-originals` bucket through the Storage API, then run
`uv run --locked alembic downgrade 0004`. The migration refuses rollback while
the bucket exists. The downgrade removes discovery sessions, import audit and
segments. Deploy the previous app revision before re-enabling traffic. To
recover, reapply revision `0005` and restore the archived database rows and
originals under their original paths together.
