# DemoForge AI — Sequential Claude Code / Cursor Prompts

## Operating instructions
Run these prompts one at a time in repository root. After each prompt, review the diff, run tests, and commit. Provide `01_PRD.md` and `02_ARCHITECTURE.md` as context. Never give the agent production credentials, real customer transcripts, or permission to skip tests. If an integration capability is undocumented, implement an adapter stub and manual fallback rather than inventing an API.

## Prompt 0 — Repository instructions
```text
You are the staff engineer building DemoForge AI. Read docs/01_PRD.md and docs/02_ARCHITECTURE.md first. Create AGENTS.md with architecture decisions, coding conventions, security invariants, tests and definition of done. Require incremental changes, migrations, strict typing, clear error handling, and tests for each feature. Never commit secrets or real customer data. Do not implement future-phase features without approval. Before editing, summarize the plan and list files to change. After editing, run available checks and report exact results, remaining risks and next steps.
```

## Prompt 1 — Scaffold and developer experience
```text
Build the monorepo skeleton from the architecture. apps/web: Next.js App Router, TypeScript, Tailwind, shadcn/ui; services/api: FastAPI with Pydantic, SQLAlchemy and Alembic; services/worker: durable job worker interface; packages/contracts: versioned JSON schemas; docs and tests. Add docker-compose for local dependencies, .env.example with placeholder values, Makefile or task scripts, health endpoints, GitHub Actions lint/typecheck/tests and README setup. No mock endpoints masquerading as real features. Validate clean install and startup; fix failures.
```

## Prompt 2 — Identity, workspaces and authorization
```text
Implement Supabase Auth integration, JWT verification in FastAPI, workspaces, memberships and roles (admin, product_admin, sales_engineer, viewer). Add Postgres migrations and RLS on every tenant-owned table. Write integration tests proving workspace A cannot read or mutate workspace B records, including through direct API IDs and storage paths. Add sign-in, workspace switcher if authorized, and protected routes. Do not trust client-provided workspace IDs. Provide migration and rollback instructions.
```

## Prompt 3 — Opportunities dashboard
```text
Implement opportunity CRUD with workspace isolation, owner, company, stage, product, target demo date and notes. Build responsive opportunities list, create/edit form, detail screen, empty/loading/error states and optimistic updates only where safe. Add input validation, pagination, sorting and tests. Use polished enterprise UI with light/dark themes, accessible keyboard controls and no dead buttons. Provide screenshots or describe UI verification steps.
```

## Prompt 4 — Discovery ingestion
```text
Implement discovery sessions and source documents. Support paste transcript, TXT, MD, DOCX and text-based PDF upload; store originals privately and extracted text as ordered segments with stable IDs, speaker/timestamps when present. Enforce size and MIME limits, safe parsing, dedupe by content hash and actionable errors for scanned PDFs. Support optional Plaud summary as separate source. Add transcript viewer with source anchors and provenance. Build a PlaudImportAdapter interface but do not claim direct Plaud sync. Add parsing and security tests.
```

## Prompt 5 — Discovery AI and evidence
```text
Build asynchronous discovery analysis using a provider-agnostic LLM interface with OpenAI implementation and deterministic fake provider for tests. Extract pain points, goals, requirements, personas, integrations, objections, metrics, constraints, success criteria and unknowns using strict Pydantic schema. Every asserted finding must reference actual transcript segment IDs; reject fabricated IDs, label inference, store confidence and prompt/model version. Treat transcript text as untrusted, resist prompt injection, enforce retries and token/cost limits. Build review/edit/approve UI. Test contradictory statements, missing data, malicious embedded instructions and model failures.
```

## Prompt 6 — Discovery gaps and approval
```text
Implement RequirementsNormalizer and discovery gap analysis from approved insights only. Show prioritized missing questions, rationale, affected requirements and owner/status. Allow manual additions, edits and approval; keep audit history and preserve source links. Prevent downstream storyboard generation from silently using unapproved AI assertions. Add API and UI tests for state transitions and permissions.
```

## Prompt 7 — Product capability catalog and mapping
```text
Implement product capability catalog with version, support status, limitations, integration dependencies and documentation provenance. Build admin CRUD and search. Implement capability mapping of approved requirements into supported/partial/unsupported/unknown with rationale and exact catalog refs. Never infer product support from customer statements alone. Provide mapping review UI and tests that unknown or missing catalog entries cannot become supported.
```

## Prompt 8 — Demo storyboard generator
```text
Build StoryboardPlanner that accepts approved requirements, reviewed mappings, audience, desired demo duration and business outcomes. Generate ordered scenes with time allocations summing to target duration, demo actions, narrative/talk track, expected outcome, synthetic data needs, product evidence, unresolved gaps and demo risks. Validate schema, provenance and unsupported-feature warnings. Build Demo Studio with reorder/edit/regenerate-one-section/versioning/approval. Preserve user edits across regeneration. Include unit and end-to-end tests.
```

## Prompt 9 — Export and readiness
```text
Add Markdown and PDF storyboard exports with opportunity context, agenda, talk track, source-linked requirements, product limitations, demo prep checklist and approval status. Implement readiness checklist and blockers; do not label unapproved or unsupported scenarios demo-ready. Log exports and access events. Test output content and authorization. Use a consistent polished document layout.
```

## Prompt 10 — Plaud automation adapter (conditional)
```text
Investigate currently supported Plaud-to-Zapier or other officially documented export/trigger methods using supplied documentation only. Present confirmed integration contract and gaps before writing code. If feasible, add feature-flagged inbound integration endpoint with authentication/signature validation appropriate to the actual provider, idempotency, deduplication, audit trail and retries. If not verified, ship a generic authenticated import endpoint and manual Plaud export workflow, explicitly documenting the limitation. Never invent a Plaud public API.
```

## Prompt 11 — Hardening, evaluation and deployment
```text
Run full test suite, static analysis, dependency vulnerability checks and end-to-end synthetic healthcare scenario. Add evaluation fixtures for extraction precision, evidence validity, mapping correctness, unsupported-feature refusal and storyboard usefulness. Instrument job duration, cost and failure rate without logging customer content. Review RLS, object permissions, retention/deletion, consent messaging, accessibility and error states. Create staging deployment instructions for Vercel web, managed FastAPI and worker, Supabase; document rollback, environment variables and launch checklist. Report any unverified controls rather than claiming compliance.
```

## Suggested first command
Copy these files into a fresh repository's `docs/` folder, open the repository in Claude Code or Cursor, then run Prompt 0 followed by Prompt 1. Commit at every completed checkpoint.
