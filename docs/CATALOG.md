# Product capability catalog and review

Use **Product capability catalog** from a workspace to select a named product
release or search its capability names, descriptions, limitations, integration
dependencies, requirement phrases, and source details. Workspace and product
admins can create releases and create, edit, or archive capabilities. Sales
engineers can read the catalog. Each release identifies one product version.
Create another release to document another version. Each capability edit or
archive appends a revision and preserves the previous documentation reference.

Record a support status, a description, any integration dependencies, and a
documentation title, HTTPS URL, and section or anchor. Supply limitations for
partial and unsupported capabilities. Use documentation available to the
workspace team. DemoForge stores the citation and opens the link in the
reviewer's browser.

## Mapping and review

Open **Capability mapping** from an opportunity and select a product release.
Workspace admins and assigned sales engineers can generate, edit, and confirm
mapping drafts on active opportunities. Other sales engineers in the workspace
can read the review. The release selection identifies the catalog evidence
and is independent of the free-text product field on the opportunity.

Only the current, approved revision of each requirement enters mapping. A
draft takes its classification from an active capability in the selected
release when exactly one entry has a matching whole requirement phrase. The
comparison ignores letter case, repeated whitespace, and terminal punctuation.
Missing or ambiguous matches produce `unknown`. A reviewer can resolve an
ambiguous match by choosing a current revision with the exact documented
phrase. The classification comes from the catalog revision, with the catalog
limitations, dependencies, and citation visible alongside the rationale.

Confirm a draft after reviewing its rationale and source. Edits create a new
draft revision. An edited or archived capability makes mappings pinned to the
previous revision stale. Refresh the evidence or clear it to record `unknown`,
then confirm the new mapping revision. Requirements revised after approval
need approval again before they can be mapped.

The reviewed handoff is `GET /v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/capability-mappings/{release_id}/reviewed`.
It returns only confirmed mapping revisions with current approved requirements
and current catalog evidence, plus confirmed `unknown` mappings without an
evidence reference. Downstream consumers should carry the release, requirement,
mapping, and capability revision identifiers and re-check eligibility when
using them. An `unknown` classification represents a gap in product evidence.

## Verify and roll back

Use the local Supabase setup and database roles from [Requirements and gaps](PLANNING.md),
then run `make migrate` to apply `0008`. The catalog needs no additional
environment variables or external services. The existing Supabase integration
and browser suite exercises the catalog against real Auth and Postgres.

For a manual check, create a release with a supported capability and a second
capability documented as unknown. Enter complete phrases matching two approved
requirements, and leave another approved requirement unmatched. Verify search,
then generate and review mappings. Expect the documented classifications, an
`unknown` result for the unmatched requirement, and exact references in the
review. Edit the supported capability and verify the mapping shows stale
evidence until refreshed and reviewed. Check the same opportunity as an
unassigned sales engineer for read-only access.

Before rolling back, stop catalog and mapping writes and back up their history.
Restore the previous compatible web and API versions and run
`uv run --locked alembic downgrade 0007` with the migration credential. This
removes catalog releases, capability revisions, mappings, and mapping approvals.
Restore that history after reapplying `0008` if needed.
