# Storyboard exports and readiness

Open **Demo Studio** from an opportunity and select a storyboard revision. The
**Demo readiness** panel reports the current approval, product support, and
preparation status. Workspace admins and the assigned sales engineer can record
or reopen fictional data preparation, rehearsal, and risk review on the current
revision of an active opportunity. Prep confirmations follow that exact
revision, so a new revision starts with a fresh checklist.

A storyboard is **Demo-ready** when its current revision is approved, its
opportunity is active, its scenes cover the current approved requirements, its
pinned evidence is fresh, each scene has full catalog support, linked discovery
questions have approved resolutions, and its prep checklist is complete. The
panel lists each blocker. Review newer requirements and mappings before
representing a historical storyboard as current.

Each approved revision exposes **Download Markdown** and **Download PDF** to the
same workspace roles that can read the storyboard. An approved revision may
still export with **Not demo-ready** and its blockers. Both formats include
current opportunity context, the pinned agenda and talk track, exact protected
requirement revision links, documented limitations, prep checks, and approval
status. Each download timestamps its readiness assessment. The files contain
storyboard and opportunity brief text. They omit private opportunity notes,
original transcripts, and catalog URL query tokens.
Requirement and gap links use the configured web origin and require sign-in.

## Setup and verification

Install the DejaVu Sans system fonts on the API host and on machines running the
PDF tests. On Ubuntu or Debian, install `fonts-dejavu-core`. The renderer uses
`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` from
that package. These fonts cover Latin, Greek, and Cyrillic. Use Markdown to retain
characters outside the installed font's coverage. ReportLab is pinned by
`uv.lock`. Rendering uses controlled local fonts and page templates.

Set `EXPORT_WEB_ORIGIN` to the public HTTPS origin of the signed-in web app,
for example `https://demo.example.test`. It defaults to `http://localhost:3000`
for local development and accepts HTTP only for loopback. Run `make migrate`
with the migration credential to apply `0010` after `0009`.

Use the [disposable API and Chromium suite](PLANNING.md#setup-verification-and-rollback)
with synthetic records. For a manual check, approve one revision containing an
unknown mapping, complete prep, and expect **Not demo-ready** in the panel and
both files. Verify the citation opens the exact requirement revision, then
repeat with a supported storyboard and resolve its prep and discovery blockers.
Check that a different workspace cannot download either file by URL.

## API and audit

Under the opportunity's `/storyboards/{storyboard_id}` path, use
`GET /readiness?revision=…` to read the checklist, `PUT /readiness/{task}` to
update a prep item using `{revision, complete}`, and
`GET /export?revision=…&format=md|pdf` to request a specific approved revision.
Downloads are generated in memory and marked no-store. The renderer caps input
at 150,000 characters and output at 4 MiB. PDF additionally caps rendering
at 80 pages and checks a four-second budget between pages. Shorten and reapprove
exceptionally large documents if the renderer limit is reached.

`demoforge.storyboard_export_events` records `export_generated` and
`artifact_accessed` together for each authorized delivery. The records share a
delivery ID and contain the actor, workspace, opportunity, storyboard revision,
format, byte count, timestamp, and readiness result. These events show that the
server released the response, since the browser controls the final file save.
The table stores metadata only. The API role can append audit events. Operational
access uses the protected database administration path. Prep confirmation and
reopening events are append-only in `demoforge.storyboard_prep_events`.

For rollback, stop export and prep writes, back up both event tables, restore
the previous compatible API and web release, and run
`uv run --locked alembic downgrade 0009`. The downgrade removes export and prep
history. Restore that history after reapplying `0010` if needed.
