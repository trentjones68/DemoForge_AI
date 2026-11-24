# Requirements and gaps

Open **Requirements and gaps** from a discovery session or analysis run.
Approve current finding revisions in **Discovery analysis**, then choose
**Generate drafts**. The normalizer checks all currently approved findings in
that session. It runs deterministically on the server.

- Direct, actionable findings can become requirement drafts. Approved
  inferences, contradictions, and unknowns can suggest questions for clarification.
- The normalizer flags missing decision authority, KPIs, workflow, and
  integrations. Coverage signals are conservative rules over approved text.
  Review the proposed questions before relying on the plan.
- Each finding-backed draft pins the exact approved finding revision and its
  transcript links. Repeat generation preserves drafts and manual edits for
  the same source revision. Coverage questions remain available for
  review after new evidence emerges. Close or revise them when appropriate.
- Add requirements and questions manually when needed. Questions have a
  priority, optional workspace owner, status, rationale, and up to 16 affected
  requirements in the same session. Generated questions link related
  requirements by category when available. Generated items and manual items
  both start as drafts.

Workspace admins and the assigned sales engineer can generate, create, edit,
and approve items on active opportunities. Other sales engineers in the
workspace can read the plan. A gap can be assigned to an admin or sales
engineer in its workspace. Choose an active owner or leave the gap unassigned
when editing a gap that was assigned to a former member.

Edits create a new draft revision. Approval explicitly pins the current
revision and records the reviewer and time. Revision history keeps the
previous content, owner, status, affected links, actor, and approvals. The
history panel shows the latest 50 revisions. A stale edit or approval returns
a conflict so the reviewer can refresh and review the latest version.

## Approved inputs for downstream features

Use the approved-only endpoint as the requirements handoff to capability
review and storyboard generation:

```text
GET /v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/approved-requirements
```

It returns only current, approved requirement revisions for that opportunity.
An edited requirement needs fresh approval. A finding-backed requirement
becomes stale when its pinned finding is superseded, even if the requirement
itself has an approval record. It drops out of the handoff until a replacement
has been generated from current evidence and approved. Older jobs with distinct
findings remain independent sources. Manual requirements also require an
explicit approval, and carry no AI source reference.

Pin the returned requirement IDs and revisions when constructing downstream
work, and revalidate them before publishing new results. The tenant-scoped
database view `demoforge.approved_storyboard_requirements` enforces the same
approval and freshness checks. A session can contain up to 100 planning items.
Normalization rejects sessions with more than 100 currently approved findings
so it cannot silently infer missing coverage from truncated evidence.

## Setup, verification, and rollback

Provision the worker role per [Discovery analysis](ANALYSIS.md), then run
`make migrate` to apply revision `0007`. No additional runtime settings are
needed. To exercise the UI, use the disposable Supabase instructions and run:

```sh
npm ci
npx playwright install chromium
make build
DEMOFORGE_BROWSER_TEST=1 uv run --locked python tests/run_local_supabase.py "$status_file"
```

The browser test uses synthetic accounts against a disposable stack. Set
`DEMOFORGE_BROWSER_EXECUTABLE` to use a system Chromium installation. The
Supabase CI job runs the API and browser checks before verifying migration
rollback.

Before removing revision `0007`, stop planning writes and back up the planning
tables. Run `uv run --locked alembic downgrade 0006` using the migration
credential and deploy the preceding application revision. This removes
planning and approval history while preserving discovery analysis and
transcript evidence. Restore planning history only after reapplying `0007`.
