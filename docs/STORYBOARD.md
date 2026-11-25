# Demo Studio

Open **Demo Studio** from an opportunity. Select a product release, enter the
intended audience and one to five business outcomes, and choose a duration of
1–180 whole minutes. Each currently approved requirement must have a current,
reviewed mapping for that release before generation. A storyboard holds one
scene per approved requirement, up to 40. Allow at least one minute per scene.
Use a separate storyboard for a new audience, release, brief, or newly approved
requirements. An opportunity can have up to 25 storyboards, each with up to 250
revisions.

The planner runs synchronously and uses deterministic templates. It orders
scenes by requirement priority and distributes the selected time budget. Each
scene carries the exact approved requirement, reviewed mapping, catalog
citation and limitations when present, and any approved unresolved discovery
gaps linked to the requirement at planning time. For a partial, unsupported,
or unknown mapping, review the system warning and use the generated actions as
discussion notes. Synthetic data needs describe fictional inputs to prepare.

## Edit, refresh, and approve

- **Reorder and time scenes** uses keyboard-accessible up/down buttons and saves
  the order and all scene durations together. The sum must equal the brief.
- **Edit scene** changes the title, actions, talk track, expected outcome,
  synthetic data needs, or demo risks. Product evidence and warnings stay pinned.
- **Preview regeneration** proposes new copy and evidence for that scene. Use
  **Apply proposal** to accept it. Manually edited fields, all other scenes,
  scene order, and time allocations are retained by default. Select the explicit
  replacement option to adopt the entire proposed copy for that scene. If the
  base revision or the approved inputs change, open a fresh preview.
- **Approve revision** records the actor and time on the exact current revision.
  Acknowledge any support warnings to approve. An edit creates a draft while
  the older approval stays in history. If a requirement or reviewed mapping is
  superseded, the scene retains its previous references and shows stale evidence.
  Review the current mapping and use regeneration to refresh the affected scene.
  Approval confirms review of the plan, including its documented caveats.

Workspace admins and assigned sales engineers can edit or approve active
opportunities. Workspace sales engineers with read access can inspect the
storyboard and its history. Next.js forwards the signed-in user's identity,
and FastAPI and Postgres enforce workspace and operation authorization.

## API and operation

The API is scoped to `/v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/storyboards`.
List and create on the collection. Read `/{storyboard_id}` with an optional
`revision` query parameter to load any immutable version, its history, and the
latest revision number. Approval and evidence freshness are separate response
fields. Export consumers must pin a revision and check both before treating it
as current and approved. The revision wire contract is
[`storyboard.schema.json`](../packages/contracts/v1/storyboard.schema.json).

Run `make migrate` with the migration role to apply `0009` after `0008`. The
feature uses existing Auth and database configuration. To verify against
synthetic data, run the [disposable API and Chromium suite](PLANNING.md#setup-verification-and-rollback).
For manual verification, generate a storyboard containing a supported and an
unknown scene. Check total duration, documentation links, and the warning.
Reorder the scenes, edit a talk track, and approve after acknowledging the
warning. Edit the linked catalog capability, review the new mapping, then
preview and apply regeneration. Confirm the edited talk track is retained,
the new revision is a draft, and its predecessor remains in revision history.

For rollback, stop storyboard writes, back up storyboard and approval tables,
restore the previous compatible web and API, and run
`uv run --locked alembic downgrade 0008`. This removes storyboard history and
approval records. Restore the backup after reapplying `0009` if needed.
