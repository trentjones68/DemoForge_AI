# DemoForge AI — Product Requirements Document
Version 1.0 | 2026-11-18 | MVP

## 1. Product vision
Turn Plaud meeting transcripts and notes into evidence-backed, approved customer requirements and editable demo storyboards. Phase 2 can use approved storyboards to configure real demo tenants through narrowly scoped product-specific adapters.

## 2. Personas
- Sales Engineer: owns opportunities, discovery review, storyboard and demo readiness.
- SE Manager: visibility into pipeline demo readiness, templates, and quality.
- Product Admin: maintains approved capability catalog, product versions, constraints, and templates.
- Workspace Admin: manages users, roles, integration settings, retention and audit logs.

## 3. Scope
### MVP included
- Organization/workspace isolation, Supabase Auth, RBAC.
- Opportunity create/read/update/archive, status and ownership.
- Discovery session create, transcript TXT/MD/DOCX/PDF upload, paste text, Plaud summary upload; maintain original files and extracted text.
- Plaud import adapter with manual upload as baseline; optional Zapier/webhook adapter behind feature flag only after integration feasibility is validated.
- AI extraction with citations to source transcript segments, confidence, explicit unknowns and user-editable approval.
- Pain points, business goals, personas, requirements, integrations, security constraints, buying criteria, metrics, objections, unanswered questions.
- Discovery follow-up questions and gap analysis.
- Versioned product capability catalog, supported/partial/unsupported/unknown mappings with evidence and caveats.
- Editable storyboard with sections, time budget, use case, demo steps, talk track, product evidence, data needs, objections and risks.
- Regenerate individual storyboard sections, preserve user edits, approval and export to Markdown/PDF.
- Audit log, basic metrics, errors, async job status, retry, accessible responsive UI.

### Not MVP
- Real-time recording, speech-to-text, automatic Plaud account sync without confirmed supported integration.
- Automated product tenant configuration, executable demo scripts, Salesforce writeback, auto-emailing customer data, multi-agent autonomy without human approval.

## 4. User journey
1. SE signs in and creates opportunity with company, product, stage, date and primary use case.
2. SE imports Plaud transcript and optionally Plaud summary; file provenance and timestamps stored.
3. Processing extracts text, segments by speaker/timestamp when available; asynchronous AI job starts.
4. AI returns structured insights with evidence anchors and confidence; uncertain points clearly flagged.
5. SE edits and approves requirements; unresolved gaps are surfaced as follow-up questions.
6. Capability mapping checks approved product catalog and flags gaps, never fabricates support.
7. SE selects audience, meeting duration, and focus outcomes; generates storyboard.
8. SE edits/approves sections and exports; changes are versioned.

## 5. Functional requirements & acceptance criteria
| ID | Priority | Requirement | Acceptance criterion |
|---|---|---|---|
| FR-01 | P0 | Workspace authentication & isolation | Cross-workspace access returns 403/404; DB RLS tests pass. |
| FR-02 | P0 | Opportunity CRUD | Authorized SE can create, edit, list, archive own/workspace opportunities. |
| FR-03 | P0 | Upload & paste discovery | TXT, MD, DOCX, text-based PDF accepted; unsupported/scanned PDF gives actionable error; file limits enforced. |
| FR-04 | P0 | Preserve source evidence | Original stored privately; extracted segments have stable IDs and offsets/timestamps if available. |
| FR-05 | P0 | Structured AI extraction | JSON schema validation; every asserted insight has source segment IDs or marked inference/unknown. |
| FR-06 | P0 | Review and approval | AI suggestions remain draft until human approves; edits persist and are audited. |
| FR-07 | P0 | Gap analysis | Missing buyer, KPI, workflow or integration facts yield prioritized follow-up questions. |
| FR-08 | P0 | Product knowledge | Admin can create capabilities with version, status, limitations and documentation provenance. |
| FR-09 | P0 | Requirement mapping | Each mapping has support classification, rationale and capability reference; missing evidence is unknown. |
| FR-10 | P0 | Storyboard | Configurable duration; section durations sum to target; every demo section maps to approved needs. |
| FR-11 | P0 | Storyboard editing/export | Reorder/edit sections; export Markdown and PDF; export retains caveats. |
| FR-12 | P0 | Async processing | Jobs expose queued/running/succeeded/failed; retry idempotent; errors do not leak sensitive text. |
| FR-13 | P0 | Auditability | Approval, source import, edits, mapping changes and export events recorded. |
| FR-14 | P1 | Plaud automation adapter | Feature-flagged webhook, signature verification when provider supports it, deduplication and manual fallback. |
| FR-15 | P1 | Template library | Reusable storyboard structures by audience/use case. |
| FR-16 | P1 | Metrics | Time to first storyboard, edit rate, source coverage, approval time and error rate. |

## 6. Nonfunctional requirements
- Security: least privilege, Supabase RLS, encryption in transit and at rest, secret manager, signed URLs, upload validation, rate limits, no secrets in logs.
- Privacy: explicit customer consent and recording policy; configurable retention and deletion; no raw customer data in demo synthetic datasets; LLM provider data processing review.
- AI safety: prompt injection defenses treat transcript and uploaded content as untrusted data; structured outputs, validation, bounded retries, no arbitrary tool execution; no fabricated citations.
- Performance targets (to validate): typical text transcript processed under 2 minutes; storyboard generation under 60 seconds; 95th percentile interactive API under 800ms excluding AI jobs.
- Reliability: resumable jobs, idempotency keys, status and failure recovery.
- Accessibility: WCAG 2.2 AA target; keyboard and screen-reader support.
- Observability: request IDs, job IDs, token usage, cost estimates, latency and failure categories; redact sensitive content.

## 7. UI screens
1. Sign in / workspace onboarding.
2. Opportunities list and opportunity detail with stage, owner and progress.
3. Discovery import, transcript viewer with clickable evidence segments, AI insights and approval controls.
4. Discovery gaps and prioritized follow-up questions.
5. Product knowledge admin: capability catalog and source documents.
6. Capability mapping review with supported/partial/unsupported/unknown statuses.
7. Demo Studio: audience, duration, goals, sections, script, risks, edit and export.
8. Settings: members, roles, privacy, retention, model/provider and integration status.

## 8. Key entities
Workspace, Membership, Opportunity, DiscoverySession, SourceDocument, TranscriptSegment, ExtractionRun, Insight, Requirement, RequirementApproval, FollowUpQuestion, Product, ProductCapability, CapabilityMapping, Storyboard, StoryboardSection, Export, ProcessingJob, AuditEvent.

## 9. KPIs
- Median discovery-to-first-storyboard elapsed time.
- Manual prep hours per opportunity (baseline vs pilot).
- % approved insights supported by direct source evidence.
- % storyboard sections mapped to approved requirements.
- User edit/rejection rate and hallucination incident count.
- SE satisfaction and demo readiness completion.

## 10. Demo data & evaluation
Use synthetic healthcare payment integrity transcript fixtures with 2M claims/month, manual audit backlog, recovery leakage, security and integration constraints. Include deliberately ambiguous claims, contradictory statements, and malicious instruction text embedded in transcripts. Verify system labels ambiguity, preserves provenance and ignores embedded instructions.

## 11. Definition of done
A new workspace user can complete the entire happy path from opportunity creation through transcript upload, approved insights, capability mapping, edited storyboard and PDF export. RLS, API auth, schema validation, security tests, integration tests and smoke tests pass. README contains setup, run, deploy and rollback steps.
