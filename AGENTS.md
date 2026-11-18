# DemoForge AI repository instructions

## Product and source material

DemoForge AI turns discovery transcripts and notes into evidence-backed customer requirements, reviewed product capability mappings, and editable demo storyboards. Read the [architecture decisions and delivery plan](docs/DECISIONS.md) before making changes. Consult the PRD v1.0 for scope and acceptance criteria, the architecture for the stack and service boundaries, and the build prompts for suggested implementation checkpoints. Begin only the milestone authorized by the current task. Record conflicts that change scope or security before proceeding with the affected implementation. [PRD](docs/01_PRD.md) · [Architecture](docs/02_ARCHITECTURE.md) · [Build prompts](docs/03_BUILD_PROMPTS.md)

- Phase 1 covers tenant-scoped opportunities, manual discovery ingestion and Plaud exports, evidence review and approval, discovery gaps, catalog and capability review, storyboard editing and approval, and Markdown/PDF export.
- Plaud automation is a separate capability gate. Manual upload and paste work without Plaud connectivity. Keep automation disabled until a documented, authenticated delivery method is verified on the intended plan and the integration is approved.
- Automated demo tenant configuration, executable demo scripts, synthetic data generation services, product write adapters, and autonomous actions belong outside Phase 1. Synthetic test fixtures are part of Phase 1. Recording, speech-to-text, CRM writeback, and automatic customer email are outside MVP scope.

## Approved stack and ownership

| Path | Responsibility |
| --- | --- |
| `apps/web/` | Next.js App Router, strict TypeScript, Tailwind, shadcn/ui. Use React Query or server actions where appropriate. Vercel is the web deployment target. |
| `services/api/` | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy or SQLModel, Alembic. Own API validation, authorization, domain transitions, and persistence contracts. |
| `services/worker/` | Managed Python worker and durable queue for critical jobs. Job state survives restarts. |
| `packages/contracts/` | Versioned JSON Schemas and checked web/API/worker contracts. Establish one authoritative schema per payload and check generated artifacts for drift. |
| `infra/`, `.github/workflows/` | Reproducible local services, CI and deployment configuration. |
| `tests/`, `fixtures/synthetic/`, `docs/` | Cross-service tests, synthetic fixtures, architecture, operation and setup documentation. |

Use Supabase Postgres, Auth, and private Storage. Use a bounded, deterministic processing pipeline with a provider adapter and OpenAI as the initial model provider. Treat pgvector and LangGraph as optional and defer adoption until a measured requirement justifies them. Keep FastAPI as the domain API for browser and server-rendered flows. A Next.js server action still uses the caller's authorization context.

## Discovery-to-export contracts

1. Ingest a pasted transcript, TXT, Markdown, DOCX, or text-based PDF. Treat an optional Plaud summary as a separate source. Preserve the private original, import provenance, and ordered segments with stable IDs, offsets, and speaker or timestamp metadata when available.
2. `DiscoveryExtractor` proposes typed findings with verified evidence references, confidence, and explicit uncertainty. `RequirementsNormalizer` uses approved insights to propose requirements and prioritized follow-up questions, preserving links to the original evidence.
3. `CapabilityMatcher` uses approved requirements and a versioned catalog to classify support as supported, partial, unsupported, or unknown. Each support claim requires an exact catalog reference and rationale. Missing evidence yields unknown.
4. `StoryboardPlanner` uses approved requirements, reviewed mappings, audience, outcomes, and target duration. Every scene links to approved needs. Section times add up to the target. Preserve manual edits and caveats through regeneration, approval, and Markdown/PDF export.

## Tenant isolation and authorization

- Verify Supabase JWT signatures and claims server-side using trusted issuer configuration. Authorize against current workspace membership and operation-specific permissions. Resolve ownership and foreign-entity scope on the server. A route, JWT metadata field, request body, object path, or queue message alone grants no authority.
- Enable RLS on every tenant-owned table, including joins, jobs, and audit records. Test read and write policies with actual non-bypass roles. Enforce same-workspace relationships with database constraints as well as application validation. Use transaction-scoped identity on pooled connections and test connection reuse. Public request handlers must use a non-owner, non-`BYPASSRLS` role.
- Keep migrations and privileged maintenance separate from request and worker credentials. Derive worker authority from a persisted job and recheck its tenant and referenced records. Scope object reads, signed URLs, exports, caches, and background results to the authorized tenant and resource. Deny by default and use consistent 403/404 behavior that avoids tenant enumeration.
- Test both happy paths and negative paths using two workspaces, including mismatched IDs, memberships, role changes, direct storage access, worker dispatch, and cross-tenant linkage as applicable. Keep privileged secrets server-side.

## Transcript, evidence, and AI handling

- Require recording/import consent controls, encryption in transit and at rest, and short-lived signed URLs issued after authorization. Keep uploads quarantined until validations pass. Validate content and type, enforce per-workspace quotas and parser limits, treat filenames and extracted markup as untrusted, and give scanned PDFs an actionable error. Exclude real customer material, credentials and PHI from code, fixtures, logs and test environments.
- Retain immutable source revisions and stable evidence IDs for approved content. Scope evidence to the correct discovery session and source revision. Validate quote spans and referenced IDs independently of the model. Distinguish directly supported findings, labeled inferences, unknowns, and contradictions. Treat confidence as a review aid.
- Treat source files, transcripts, summaries, catalog text, and model outputs as untrusted data. Extraction uses bounded structured outputs, runtime validation, budgets and timeouts. Keep tool execution disabled. Validate model output before persistence and keep suggestions in draft until an authorized human approves a specific revision.
- Derive downstream work from approved requirements and reviewed, versioned mappings. Preserve exact catalog references and caveats. Regenerate into a proposed revision for the selected section and protect concurrent edits. Keep export and readiness distinct from generation. See the [approval and export decisions](docs/DECISIONS.md#d4-evidence-approval-and-revisions).
- Audit imports, edits, approvals, mapping changes, and exports with actor, entity, and workspace context. Keep transcript text, prompts, raw provider responses, credentials, and signed URLs out of job and audit metadata. Document retention and deletion across originals, extracted text, derived records, exports, jobs, logs, provider and backups. Gate real-data use on privacy review.
- Keep secrets in environment-specific server-side secret storage. Use placeholders in `.env.example` and document which settings are public. Keep privileged keys and connection strings out of browser bundles, fixtures, and CI output.

## Coding standards

- Keep TypeScript strict and Python typed at public and service boundaries. Enforce strict Python typing in CI, validate all external inputs at runtime, and avoid unchecked casts or implicit `any`. Use explicit enums, error codes, input limits and status transitions. Reject schema drift and avoid leaking internal errors.
- Keep authorization and state transitions in the API's domain logic. Reuse shared contracts and keep adapters responsible for translating provider data. Handle provider failures with stable error codes and actionable UI feedback.
- Make migrations forward-compatible where possible. Document migration order, data impact, and downgrade or restore procedures. Test on clean and existing schemas as applicable. Keep dependency versions pinned through lockfiles and use repeatable CI commands.
- Persist queued, running, succeeded, and failed job states. Apply bounded retries only to retryable failures. Use durable idempotency and atomic transitions for jobs, imports, and approvals. Prefer redacted structured logs with request and job IDs.
- Use accessible controls, keyboard navigation and visible focus. Cover loading, empty, permission-denied and failure states. Use the deterministic fake model only for tests and explicitly labeled development flows.

## Testing rules

- Run applicable lint, formatting, strict type checks, and unit, migration, integration, and smoke tests. Use real local DB and Storage policies for authorization tests. Exercise user-facing flows in a browser, including keyboard interaction and failure states.
- Use synthetic discovery fixtures with ambiguous and contradictory statements, missing facts, and embedded hostile instructions. Verify rejection of fabricated citations, malformed outputs, and out-of-scope references. Cover replay and interruption for asynchronous side effects and concurrent edits for versioned approvals.
- Before release, exercise the synthetic workflow from sign-in and opportunity creation through import, approved requirements, capability mapping, storyboard editing, and PDF export. Run the security and privacy gates in the [delivery plan](docs/DECISIONS.md#phase-1-milestones).

## Development workflow and Definition of Done

1. Inspect the checkout, identify the authorized milestone, and state the affected paths and acceptance checks before editing.
2. Deliver one independently verifiable slice. Update affected contracts, migrations, tests, and operational instructions with the change. Use the documented local setup and synthetic fixtures.
3. Review the diff and run the milestone's acceptance checks and applicable negative tests. A milestone is done when those checks pass, required configuration and commands are documented, and operational changes have a recovery path. Keep setup, run, deployment, and rollback instructions current.
4. Report exact check results and any unrun checks, blockers, or remaining risks. Commit or deploy only when authorized.
