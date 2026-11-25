# DemoForge AI

DemoForge AI helps sales engineers turn discovery evidence into reviewed
requirements and demo storyboards. The Foundation milestone includes Supabase
sign-in, workspace membership and authorization, API health probes, local
database tooling, and the worker and schema contracts for later milestones.

## Local setup

Install Docker with Compose, Make, Node and npm at the versions specified in
`.nvmrc` and `package.json`, and uv 0.13.6. uv uses the Python version in
`.python-version`.

Install the DejaVu Sans fonts before running PDF exports or `make check`.
On Ubuntu or Debian, install the `fonts-dejavu-core` package.

```sh
cp .env.example .env
make install
make db-up
make migrate REVISION=0002
```

If your home directory is read-only, set `npm_config_cache` and `UV_CACHE_DIR`
to writable paths before running the commands.

The example DSNs work with the loopback-only disposable Compose database. Use
them only for local development. The API uses a restricted database role and
Alembic uses a separate migration role. If you change a port or password,
update the corresponding DSNs to match. Keep real credentials in secret
storage, outside example files and client-side configuration.

In separate terminals, run `make web` for port 3000 and `make api` for port
8000. The API serves `GET /health/live`, which checks process liveness, and
`GET /health/ready`, which returns 200 after a real Postgres query or 503 if
the connection is unconfigured or unavailable. The probes expose no
connection details. Stop the dev servers with Ctrl-C and the database with
`make db-down`. This preserves the database volume.

For the full identity workflow, install Supabase CLI 2.80.0 separately and
use `make supabase-up`. Run `supabase status` for local connection settings.
Keep the request and migration DSNs separate when configuring `.env`. Stop
the stack with `make supabase-down`. [Local dependencies](infra/README.md) · [Identity setup and permissions](docs/IDENTITY.md)

## Development checks

```sh
make check    # Lint, strict TypeScript and Python checks, unit and contract tests
make test-integration # Run against Compose Postgres migrated to 0002
make build    # Production Next.js build
make smoke    # Run with web, API and database already running
```

CI repeats the checks from locked dependencies, verifies migration upgrade
and downgrade, and runs smoke checks against a built web app and real local
Postgres. A separate job exercises local Supabase Auth and Storage, the
Postgres-backed discovery worker, the synthetic healthcare evaluation, and
Chromium.

## Deployment and rollback

The staging runbook covers Vercel or managed Node for the web app, managed
FastAPI and worker hosting, Supabase roles and Storage, environment variables,
launch verification, and rollback. [Staging runbook](docs/STAGING.md)

The release verification record covers the healthcare evaluation, dependency
audits, telemetry, and the controls that still require hosted or operator
verification. [Release verification](docs/RELEASE_VERIFICATION.md)

[Architecture and milestone plan](docs/DECISIONS.md) · [Engineering instructions](AGENTS.md)

[Opportunities dashboard setup and verification](docs/OPPORTUNITIES.md)

See [Discovery ingestion](docs/DISCOVERY.md) for upload and paste setup, private
originals, limits, verification, and rollback.

See [Discovery analysis](docs/ANALYSIS.md) for the separate worker, provider
configuration, evidence review, and rollback.

See [Requirements and gaps](docs/PLANNING.md) for normalization, revision
approval, the approved-only downstream contract, and browser verification.

See [Product capability catalog and review](docs/CATALOG.md) for product
releases, documented support, mapping review, and rollback.

See [Demo Studio](docs/STORYBOARD.md) for storyboard generation, provenance,
revision approval, verification, and rollback.

See [Storyboard exports and readiness](docs/EXPORTS.md) for Markdown and PDF
downloads, preparation and approval gates, rendering setup, and audit events.

See [Plaud imports](docs/PLAUD.md) for the documentation review, manual export
workflow, and authenticated JSON import contract.
