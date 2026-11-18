# DemoForge AI — Technical Architecture

## Architecture overview
- Web: Next.js App Router, TypeScript, Tailwind, shadcn/ui, React Query or server actions where appropriate.
- API: FastAPI, Python 3.12+, Pydantic v2, SQLAlchemy/SQLModel, Alembic migrations.
- DB/auth/storage: Supabase Postgres + RLS, Supabase Auth, private Supabase Storage; pgvector optional for catalog retrieval, not required for first MVP.
- Background jobs: managed queue/worker (e.g. Redis + RQ/Celery or cloud queue) with durable retries; never rely on in-process FastAPI background tasks for critical jobs.
- LLM: provider adapter with OpenAI initially; versioned prompts and JSON-schema/Pydantic outputs; LangGraph optional for stateful orchestration, use a deterministic pipeline first.
- Hosting: Vercel web, managed Python API + worker, managed Postgres and storage.

## Processing pipeline
Upload -> MIME/size validation -> private object store -> text extraction -> segment index -> structured extraction -> evidence verification -> human review -> capability mapping -> human review -> storyboard generation -> edit/approval -> export.

## Plaud ingestion contract
Input interface: {provider, external_id?, session_date?, title, transcript_text?, summary_text?, file_id?, speaker_segments?, timestamps?, metadata}. Manual file/paste works first. Future webhook integration must be verified against actual Plaud/Zapier capabilities before implementation; never invent Plaud endpoints or assume transcript delivery is available on all plans. Require authorization, dedupe by workspace/provider/external_id/content_hash, and log import provenance.

## Agent contracts
- DiscoveryExtractor: transcript segments -> insights with type, quote/segment_ids, confidence, inferred boolean, rationale.
- RequirementsNormalizer: approved insights -> requirements, priority, stakeholders, constraints, gaps.
- CapabilityMatcher: requirements + versioned catalog -> supported/partial/unsupported/unknown, refs and rationale; no support claim without catalog evidence.
- StoryboardPlanner: approved requirements + mapping + audience + minutes -> ordered scenes and talk tracks, data requirements, expected outcomes, risk flags.
- Later: SyntheticDataGenerator, TenantConfigurator, DemoValidator with human authorization and restricted adapter APIs.

## Minimal schema (illustrative)
- workspaces(id,name,created_at)
- memberships(workspace_id,user_id,role)
- opportunities(id,workspace_id,owner_id,name,product_id,stage,created_at)
- discovery_sessions(id,workspace_id,opportunity_id,title,occurred_at,status)
- source_documents(id,workspace_id,session_id,provider,storage_key,sha256,mime_type,created_at)
- transcript_segments(id,workspace_id,source_id,ordinal,speaker,start_ms,end_ms,text)
- insights(id,workspace_id,session_id,type,statement,confidence,inferred,status,source_segment_ids jsonb)
- requirements(id,workspace_id,opportunity_id,description,priority,status,source_insight_ids jsonb)
- product_capabilities(id,workspace_id,product_id,name,version,status,limitations,source_ref)
- capability_mappings(id,workspace_id,requirement_id,capability_id nullable,support_status,rationale)
- storyboards(id,workspace_id,opportunity_id,version,target_minutes,status)
- storyboard_sections(id,workspace_id,storyboard_id,sort_order,title,minutes,steps jsonb,talk_track,data_needs jsonb,requirement_ids jsonb)
- jobs(id,workspace_id,kind,status,attempts,idempotency_key,error_code,created_at)
- audit_events(id,workspace_id,actor_id,action,entity_type,entity_id,metadata jsonb,created_at)
Every tenant-owned table must include workspace_id with RLS policies; do not trust workspace_id from browser without membership verification.

## API sketch
POST /v1/opportunities; GET /v1/opportunities; GET/PATCH /v1/opportunities/{id}
POST /v1/opportunities/{id}/discovery; POST /v1/discovery/{id}/sources; GET /v1/discovery/{id}/segments
POST /v1/discovery/{id}/analyze; GET /v1/jobs/{id}; GET/PATCH /v1/discovery/{id}/insights; POST /v1/discovery/{id}/approve
GET/POST /v1/products/{id}/capabilities; POST /v1/opportunities/{id}/map-capabilities
POST /v1/opportunities/{id}/storyboards; GET/PATCH /v1/storyboards/{id}; POST /v1/storyboards/{id}/approve; GET /v1/storyboards/{id}/export?format=md|pdf

## Security and privacy
- Verify Supabase JWT server-side; enforce role/workspace permissions in API and RLS in DB.
- All objects private with time-limited signed URLs; sanitize uploaded filenames, prevent oversized/decompression-bomb uploads, and scan when infrastructure allows.
- Treat transcripts as hostile input: instruction hierarchy in prompts, no external tool access during extraction, evidence validators, JSON schema and output length bounds.
- No real patient PHI in fixtures or demo environments. Customer transcripts may contain regulated data: establish data processing agreements, retention, regional controls and compliance review before production ingestion.
- No autonomous production writes. Phase 2 uses demo-only tenant adapters, explicit approval and rollback.

## Repository structure
apps/web/ ; services/api/ ; services/worker/ ; packages/contracts/ ; infra/ ; docs/ ; tests/ ; fixtures/synthetic/ ; .github/workflows/.

## Release gates
- Local docker compose and documented env.example.
- CI lint/typecheck/unit/integration/security checks.
- Staging deployed with synthetic fixtures.
- End-to-end happy path and cross-tenant negative tests.
- Human signoff for AI output quality and privacy posture.
