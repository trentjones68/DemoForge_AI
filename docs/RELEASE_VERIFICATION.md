# Release verification

## Synthetic evaluation

The healthcare payment integrity transcript and its expected labels are kept
under `fixtures/synthetic/evaluation`. The corpus includes a manual audit
backlog, conflicting volumes of 2,000,000 and 1,700,000 claims per month,
fictional integration and security constraints, a deliberately omitted budget,
and an embedded instruction to invent support. [Transcript](../fixtures/synthetic/evaluation/healthcare-payment-integrity.txt) · [Expected results](../fixtures/synthetic/evaluation/healthcare-payment-integrity.expected.json)

| Dimension | Assertion |
| --- | --- |
| Extraction precision | The deterministic provider emits the golden findings with zero extras or duplicates. The two volumes remain contradictory and the budget remains unknown. |
| Evidence validity | Exact persisted citations resolve to the imported source and expected segment. Fabricated references and mismatched evidence are covered in the provider and worker suites. |
| Mapping correctness | Exact catalog evidence produces supported and unsupported mappings. An unmatched integration stays unknown. |
| Unsupported-feature refusal | The plan supplies discussion actions and warnings for unsupported and unknown requests. Acknowledgment is required for approval, and completed preparation leaves the plan marked **Not demo-ready**. |
| Storyboard usefulness | All approved requirements have a timed scene. The agenda sums to the requested duration, each scene reflects the audience and outcome, and fictional data needs, risks, limits and manual edits survive PDF export. |

The fixture evaluates the deterministic pipeline and its review boundaries.
Hosted OpenAI extraction quality and provider handling of the embedded
instruction require a separate synthetic smoke and human scoring.

Run `make check`, `make test-integration` against disposable Postgres at `0002`,
`make build`, and `make smoke` with local services running. Run the disposable
Supabase suite with `DEMOFORGE_BROWSER_TEST=1` and a production web build. This
covers authenticated healthcare import through actual private Storage, worker,
requirement and mapping approvals, and PDF delivery. The Chromium scenario
covers sign-in, keyboard consent, evidence links, revision editing, downloads,
and tenant denial. Use `PYTEST_ADDOPTS=-s` to print local synthetic timings.
These measurements are single-fixture timings; hosted workload and API p95
need measurement on staging. [Disposable setup](IDENTITY.md#verification-and-rollback)

The local release-hardening run passed 94 tests across the unit, Postgres, and
Supabase suites, including Chromium. The healthcare scenario matched all six
expected findings and produced three scenes. Import through evidence review
took 306 ms and storyboard generation took 72 ms on the disposable local stack.
Lint, strict type checks, production build, startup smoke, migration upgrade
and rollback, dependency audits, and the changed-file secret scan passed.

For dependency checks, run `npm audit --audit-level=high` and audit the pinned
Python production dependencies. Keep the exported dependency list temporary.

```sh
reqs=$(mktemp)
trap 'rm -f "$reqs"' EXIT
uv export --locked --format requirements.txt --no-emit-project --no-dev --no-hashes --output-file "$reqs"
uv tool run --from pip-audit==2.10.0 pip-audit --disable-pip --no-deps -r "$reqs"
```

## Security, privacy and accessibility review

| Control | Evidence and remaining verification |
| --- | --- |
| RLS and route authorization | The disposable tests use the real API and worker roles. They cover separate workspaces, direct IDs, role revocation, pooled identity, insert policies, and a worker restricted to lease-bound functions. Revalidate actual roles, grants, pooler identity and service credentials in staging. |
| Object permissions | Direct Storage access to originals is denied even with an overlapping test policy. An authorized server-issued signed URL remains usable for up to 60 seconds. Verify private buckets, managed encryption, ingress, DNS and credential rotation in the target project. |
| Retention and deletion | Tests dispose of their own originals, rows and environment and verify migrations and rollback. Production workspace retention, deletion authorization, restoration and purge SLAs for derived rows, independent downloaded copies, backups, logs and provider data still need an approved lifecycle policy and exercised operator runbook. Membership revocation takes effect on future authorized requests. |
| Consent and input handling | API tests reject import without consent. The app records the actor and import time, and the browser tests exercise the named checkbox and keyboard interaction. The checkbox is an operator attestation. Required notice, proof, data residency, malware scanning and managed parser isolation need target-environment review. |
| Accessibility and errors | Chromium covers role-based navigation, keyboard interaction and permission/invalid-state feedback. Check screen readers, visible focus, contrast, zoom, dark mode, error recovery and multiple browsers manually before launch. A WCAG conformance audit remains open. |
| Logging and cost | Worker tests verify safe outcomes, durations and metadata. Staging still needs log and trace sink redaction, retention, and alert routing verification. Provider billing and usage reporting need validation with an approved live smoke. |

## Job telemetry

Each handled worker attempt emits a `discovery_analysis_attempt` JSON record with
schema version, job ID, provider, outcome, elapsed `duration_ms`, safe error code,
reported input and output token counts, and `estimated_cost_usd_micros`. Rates
are the configured model rates in the code, so these are estimates. Synthetic
attempts have zero provider cost. Missing usage or a provider response lost
before measurement leaves OpenAI cost `null`; track those separately from zero.
`failed_attempt` can be retried by the queue. `not_applied` means the transition
was refused by the lease or access gate. A hard process stop can leave no log
record for an attempt. Raw transcript, prompt, output, error bodies, SQL bind
values, and lease tokens are excluded from the event.

Use durable `created_at`, `completed_at`, and `status` for job duration and the
terminal failure rate, including exhausted leases eventually processed by the
queue. Use an authorized operator connection scoped to the intended workspace.
Pre-`0011` terminal rows lack a completion timestamp and are outside this
window. Run the query using a `psql` variable named `workspace`.

```sql
SELECT count(*) AS terminal_jobs,
       count(*) FILTER (WHERE status = 'failed') AS failed_jobs,
       round(100.0 * count(*) FILTER (WHERE status = 'failed')
             / nullif(count(*), 0), 2) AS failure_percent,
       round(avg(EXTRACT(EPOCH FROM completed_at - created_at)) * 1000) AS mean_job_ms
FROM demoforge.analysis_jobs
WHERE workspace_id = :'workspace'::uuid
  AND completed_at >= statement_timestamp() - interval '24 hours'
  AND status IN ('succeeded', 'failed');
```
