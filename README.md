# DemoForge AI

DemoForge AI helps sales engineers turn discovery evidence into reviewed
requirements and demo storyboards. The Foundation milestone includes Supabase
sign-in, workspace membership and authorization, API health probes, local
database tooling, and the worker and schema contracts for later milestones.

## Local setup

Install Docker with Compose, Make, Node and npm at the versions specified in
`.nvmrc` and `package.json`, and uv 0.13.6. uv uses the Python version in
`.python-version`.

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
Postgres. A separate job exercises real Supabase Auth and Storage. The worker scaffold defines a typed broker interface. Broker
selection, dispatch, retries, and job execution belong to the durable jobs
milestone.

## Deployment and rollback

Build the web app with `make build` and run its production server with
`npm run start --workspace @demoforge/web` locally. Vercel is the web deployment
target. Start the API with
`uv run --locked --no-dev uvicorn demoforge_api.main:create_app --factory --app-dir services/api --host 0.0.0.0`
on managed Python hosting. Supply the database URL through the platform's secret
store. Run `make migrate` separately with a migration credential. The scaffold
has no worker process to deploy.

Roll back a release by restoring the previous compatible web and API versions.
Back up workspace data and objects before a database downgrade. See the
[identity rollback procedure](docs/IDENTITY.md#verification-and-rollback).

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
