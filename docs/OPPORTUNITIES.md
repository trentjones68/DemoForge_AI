# Opportunities dashboard

Open a workspace and choose **Open opportunities**. The list defaults to active
opportunities and supports pagination, stage filtering, and sorting by last
update, demo date, or name. Opportunities without a target date sort after
scheduled dates. The form requires a name, company, product interest, and
stage. Target demo date, primary use case, and notes are optional. Product
interest is free text until the versioned catalog is available.

| Role | Read | Create, edit, or archive | Assign owners |
| --- | --- | --- | --- |
| Workspace admin | Workspace records | Any active workspace record | Current workspace admins or sales engineers |
| Sales engineer | Workspace records | Records they own | Self |
| Product admin or viewer | Workspace records | — | — |

New opportunities default to the current user. Removing a membership clears
its opportunity ownership and preserves the records. An admin can reassign an
active unassigned record. The owner selector identifies other members by their
workspace member ID. Archiving keeps the record and its history and makes
it read only. The list hides archived records by default. Edits and archives
use a record version and return a conflict if another request has changed it.

The API is under `/v1/workspaces/{workspace_id}/opportunities`. Collection
`GET` and `POST` list and create. Item `GET` and `PUT` read and update.
`POST /{opportunity_id}/archive` archives. Authorization uses verified
Supabase identity, current workspace membership, and independent database
RLS. Create, update, and archive write an audit entry in the same transaction.
The audit table stores actor, action, version, and timestamps without use
cases or notes.

## Migration and verification

On the migrated Supabase database, run `make migrate` to apply revision
`0004`. The bare Compose database remains at `0002` for the existing
foundation PostgreSQL checks. The full Supabase integration runner exercises
the opportunities API, its RLS policies, and migration rollback.

- Sign in with a synthetic workspace admin or sales engineer and open
  Opportunities. Check the empty state and create a synthetic opportunity.
- Check the company, product, target date, and owner on the details page.
  Edit the opportunity and confirm both the details page and list show the
  saved values. Try a stale edit in a second tab.
- Create enough synthetic records for a second page. Try sorting by name
  and demo date and filtering by stage. Check Previous and Next.
- Archive the record and confirm it disappears from Active and remains
  readable under Archived.
- At a narrow viewport, check the card list and forms for overflow. Tab
  through the controls, activate a link with Enter, and try both themes.
- As a viewer, confirm the list is readable and write controls are absent.
  Open a different workspace's opportunity by direct URL and expect denial.

To reverse revision `0004`, first stop opportunity writes, back up the
opportunity and audit tables, and verify recovery. Run
`uv run --locked alembic downgrade 0003` and deploy the previous compatible
app version. This downgrade drops the two new tables. For a deeper downgrade,
follow the separate [identity rollback procedure](IDENTITY.md#verification-and-rollback).
