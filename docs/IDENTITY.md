# Identity and workspace authorization

## Roles and workspace access

A confirmed, non-anonymous Supabase Auth account can sign in with email and
password and create a workspace. The creator becomes its admin in the same
database transaction. A signed-in user can list and switch among only their
current memberships. FastAPI authenticates every request and PostgreSQL RLS
checks workspace membership independently.

| Operation | Admin | Product admin | Sales engineer | Viewer |
| --- | --- | --- | --- | --- |
| Read the workspace and see own role | Yes | Yes | Yes | Yes |
| Rename the workspace | Yes | — | — | — |
| List, grant, change or revoke non-admin memberships | Yes | — | — | — |
| Read or write private objects in the workspace bucket | Yes | — | Yes | — |

Admins grant membership to an existing Supabase user UUID using
`PUT /v1/workspaces/{workspace_id}/members/{user_id}`. The body contains one of
`product_admin`, `sales_engineer`, or `viewer`. The same path supports `DELETE`
to revoke that membership. Account provisioning uses Supabase Auth. Email
invitations, admin transfer UI, and feature-specific grants beyond this matrix
are outside this slice. Before deleting the only admin account, have a trusted
operator transfer workspace administration. A deleted account's memberships are
removed by the Supabase foreign key.

Storage uses the private `workspace-files` bucket with keys in the form
`<workspace UUID>/<object path>`. Policies cover reads, uploads, updates and
deletions, including the destination of a move. Revocation takes effect on
subsequent authenticated API and Storage requests. Signed URLs already issued by
Storage remain valid until expiry. Use short expiry times and avoid putting
signed URLs in logs. Future transcript ingestion still requires its own consent,
retention, and data-handling controls.

## Configure and migrate

1. Use a disposable local Supabase stack with `make supabase-up`, or use the
   approved hosted Supabase project. Provision confirmed test accounts in local
   Studio, or provision production accounts through the project's approved
   process.
2. Use a migration identity that can manage the application schema and Supabase
   Storage policies. From a trusted `psql` session, create a separate API login:

   ```sql
   CREATE ROLE demoforge_api LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS;
   \password demoforge_api
   ```

   Keep this role free of broad memberships, ownership, and additional
   privileges. The migrations grant its required access. Use the direct
   database or session pooler for migrations. Use the direct database or
   session pooler for the API. The API uses transaction-local identity and
   requires the effective role to be `demoforge_api`.
3. In the ignored root `.env`, set `DATABASE_URL` for the request login and
   `MIGRATION_DATABASE_URL` for the migration login using
   `postgresql+psycopg://…` URLs. Configure the exact token issuer in
   `SUPABASE_JWT_ISSUER`, and point `SUPABASE_JWKS_URL` to the project's JWKS
   endpoint for asymmetric signing. The pinned Supabase CLI signs user access
   tokens with ES256 by default. Its standard local issuer is
   `http://127.0.0.1:54321/auth/v1`, and its JWKS endpoint appends
   `/.well-known/jwks.json` to that issuer. The expected audience defaults to
   `authenticated`. For a project configured for legacy HS256 signing, use
   `SUPABASE_JWT_SECRET` in place of the JWKS setting. Keep the legacy signing
   secret server-side.
4. Copy `apps/web/.env.example` to `apps/web/.env.local`. Configure the
   Supabase URL, its public publishable key or legacy anon key, and the
   server-side API URL. Use the same Supabase issuer for the web and API.
   Apply migrations and start `make api` and `make web` in separate terminals.

   ```sh
   make migrate REVISION=0003
   uv run --locked alembic current --check-heads
   ```

Revision `0002` introduces the workspace tables, roles, and RLS. Revision
`0003` links membership to Supabase Auth users and creates the private Storage
bucket and policies. For head, provision the
[analysis worker login](ANALYSIS.md#provision-the-worker) before migrating.
Use `make migrate REVISION=0002` only for bare Compose
Postgres tests. Full identity setup requires `0003`. Review existing
test data before upgrading from a bare database. Supabase rejects membership
rows without corresponding accounts.

## Verification and rollback

Run `make check` for the unit suite and `make test-integration` against migrated
disposable Compose Postgres. To run the real service suite against a fresh
Supabase CLI stack, capture its local credentials in a temporary file and use
the runner:

```sh
(
  umask 077
  status_file=$(mktemp)
  trap 'rm -f "$status_file"' EXIT
  supabase status -o json > "$status_file"
  uv run --locked python tests/run_local_supabase.py "$status_file"
)
```

The runner refuses databases that already have a DemoForge schema, Alembic
state or request role. It uses synthetic accounts and objects and verifies
migration reapplication and rollback. Dispose of the test stack after use.

For rollback, remove traffic from the new workspace routes and take a verified
backup of workspace rows and Storage artifacts. After preserving the artifacts,
empty and delete `workspace-files` through the Storage API. The downgrade
refuses to proceed while the bucket exists. Use `uv run --locked alembic downgrade 0002`
to reverse only Storage and the Auth foreign key, or `uv run --locked alembic
downgrade 0001` to reverse identity as well. Downgrading to `0001` drops
workspaces and memberships. Deploy the previous compatible application version
and verify startup, access and backup recovery before resuming traffic.
