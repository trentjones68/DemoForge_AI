# Staging deployment and release checks

Staging uses its own Supabase project, a Next.js deployment, managed Linux
FastAPI hosting, and a supervised Linux discovery worker. Use synthetic accounts
and transcripts on this environment. Start with the deterministic fake provider.
The hosted smoke, model quality, and privacy gates below require separate
verification before the first real-data deployment.

## Provision Supabase

1. Create a staging project and configure its Auth site URL and allowed redirect
   origins for the staging web hostname. Provision confirmed synthetic users.
   Use a separate origin and project for production. Limit preview origins to
   environments with an explicit staging access policy.
2. Provision `demoforge_api` and `demoforge_worker` as distinct restricted logins.
   Use a migration identity with permission to manage the DemoForge schema and
   Supabase Storage policies. Use the direct database or session pooler with TLS.
   Verify the effective roles, privileges, server identity, and connection options
   using the host's published connection details. [API role](IDENTITY.md#configure-and-migrate) · [Worker role](ANALYSIS.md#provision-the-worker)
3. Run `uv sync --locked` and `make migrate` in a protected deployment job from
   the same release commit, then run `uv run --locked alembic current --check-heads`.
   The current revision is `0011`. Confirm both `workspace-files` and
   `discovery-originals` are private. Apply migrations in one controlled job per
   environment before starting upgraded services.
4. Configure secret injection by service. Restrict access to the Storage service
   key, which has broader Supabase privileges than the application route. Grant
   only the ingestion and signing API process access to it.

## Deploy FastAPI and the worker

Use Python from `.python-version`, uv `0.13.6`, and `uv sync --locked --no-dev`
from the repository root. The API host needs DejaVu Sans (`fonts-dejavu-core`
on Debian/Ubuntu). Configure HTTPS ingress, authenticated rate limits, request
size limits compatible with [discovery intake](PLAUD.md#authenticated-json-import),
and a request timeout covering the app's bounded processing. Use the separate
runtime credentials below. Avoid collection of raw request URLs, bodies, cookies,
Authorization headers, signed links, and provider responses in upstream logging.

```sh
uv run --locked --no-dev uvicorn demoforge_api.main:create_app --factory \
  --app-dir services/api --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
```

Use `/health/live` and `/health/ready` for API probes. In staging, readiness
proves Postgres connectivity. Exercise Auth, Storage and downloads as separate
smoke steps. Run one or more supervised worker processes using the same release
commit and provider mode as the API. The Postgres queue owns retry and lease
recovery. Verify that the supervisor can restart the worker and give it time
to finish an in-flight request during rollout.

```sh
PYTHONPATH=services/api:services/worker uv run --locked --no-dev \
  python -m demoforge_worker.discovery
```

## Deploy the Next.js web app

For Vercel, connect the repository and choose **Next.js** with `apps/web` as
Root Directory. Enable access to monorepo files outside that directory for the
root lockfile and workspace. Select Node `24.x` and npm `11.9.0` from the project
configuration. The web build runs `npm run build` in the web workspace with
output managed by the Next.js preset. If the install command needs an override,
run `npm ci` from the monorepo root. Use staging-only Auth values and set
`API_BASE_URL` to the HTTPS API origin accessible from the Next.js server.

For a managed Node deployment, use the root workspace commands `npm ci`,
`npm run build --workspace @demoforge/web`, and
`npm run start --workspace @demoforge/web -- --hostname 0.0.0.0` behind HTTPS.
Configure the same environment variables on that service.

## Environment variables

| Service | Variable | Value or purpose |
| --- | --- | --- |
| Web | `NEXT_PUBLIC_SUPABASE_URL` | HTTPS staging project URL |
| Web | `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Public staging publishable key or legacy anon key |
| Web | `API_BASE_URL` | Server-side HTTPS API origin |
| API | `DATABASE_URL` | Restricted `demoforge_api` TLS DSN in `postgresql+psycopg://…` form |
| API | `SUPABASE_JWT_ISSUER` | Exact staging issuer, typically the project URL plus `/auth/v1` |
| API | `SUPABASE_JWKS_URL` | Exact issuer JWKS URL for asymmetric signing |
| API | `SUPABASE_JWT_AUDIENCE` | `authenticated` unless staging Auth is explicitly configured otherwise |
| API | `SUPABASE_JWT_SECRET` | Legacy HS256 fallback. Configure only when staging uses HS256 and omit `SUPABASE_JWKS_URL`. |
| API | `SUPABASE_STORAGE_URL` | Staging project Storage API origin and `/storage/v1` path |
| API | `SUPABASE_STORAGE_SERVICE_KEY` | Server-only staging Storage secret or legacy service-role JWT |
| API | `EXPORT_WEB_ORIGIN` | Exact public HTTPS staging web origin for authenticated citations |
| API and worker | `DISCOVERY_PROVIDER` | `fake` for the synthetic smoke. Use `openai` only after provider review and explicit approval. Use `disabled` on the API to pause intake. |
| API and worker | `DISCOVERY_SYNTHETIC_DEV` | `true` for the fake provider on the synthetic-only stage |
| Worker | `DISCOVERY_WORKER_DATABASE_URL` | Restricted `demoforge_worker` TLS DSN |
| Worker | `OPENAI_API_KEY` | Staging model project secret for an authorized live-provider smoke |
| Migration job | `MIGRATION_DATABASE_URL` | Separate administrator migration DSN |

## Launch checklist

- [ ] Review the release revision, migration target, backups and recovery drill.
      Check probes, roles, private buckets, issuer, web origin and cookie behavior.
- [ ] Run the synthetic healthcare walkthrough from sign-in, opportunity
      creation and consent through reviewed discovery, mappings, storyboard
      edit and PDF/Markdown download. Check contradiction, missing budget,
      unsupported recovery, and unknown integration blockers. Verify independent
      workspace denial and audit records. [Evaluation and control evidence](RELEASE_VERIFICATION.md)
- [ ] Confirm supervised worker recovery, redacted attempt telemetry, cost
      estimates, and terminal failure rate. Measure queue-inclusive analysis time,
      storyboard creation time, and interactive API p95 in staging under a
      representative workload. Compare to PRD targets of 2 minutes, 60 seconds,
      and 800 ms respectively. Record test sizes, resources and approval for any
      variance.
- [ ] Verify keyboard focus, screen-reader announcement, error state and retry
      behavior on supported browsers. Obtain live-provider quality and privacy
      approval before sending customer content. Keep Plaud automation gated on
      its separate contract review. [Plaud verification](PLAUD.md)
- [ ] Obtain sign-off on consent, data processing and retention/deletion,
      encryption, residency, scanning, rate limits, alerting, and backup recovery
      for the target deployment. Retain synthetic-only staging while gaps are open.

## Rollback

Pause new analysis by disabling the API provider, drain in-flight work where
possible, and stop the worker. Remove traffic from the release being reverted.
Back up Postgres, private originals and applicable configuration, then deploy the
previous compatible web, API and worker images as an aligned release.

Revision `0011` is additive, so the preceding application can use the upgraded
schema. If reversing the schema is required, use the migration job to run
`uv run --locked alembic downgrade 0010` after preserving the completion timing
records. That downgrade removes completion timestamps while preserving job
results and evidence. Use the feature-specific rollback procedures for deeper
reversions. Run health, authorization, import, analysis and export smoke checks
before reopening traffic. [Export rollback](EXPORTS.md#api-and-audit) · [Analysis rollback](ANALYSIS.md#rollback)
