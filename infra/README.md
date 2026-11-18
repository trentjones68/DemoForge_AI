# Local dependencies

The root Compose file runs a loopback-only Postgres instance for the scaffold's
readiness and migration checks. Use `make db-up` and `make db-down`. The named
volume persists through stops. On first startup, Postgres creates a restricted
API role alongside the migration role. Keep these credentials separate in
hosted environments as well.

For work requiring Supabase Auth or Storage, install the Supabase CLI 2.80.0
binary for your platform and verify it against the release checksum file.
[Supabase CLI release](https://github.com/supabase/cli/releases/tag/v2.80.0)

Run `make supabase-up` and `make supabase-down` with the CLI on `PATH` or set
`SUPABASE_CLI` to the verified binary path. The CLI uses `supabase/config.toml`.
If the default public ECR registry is unavailable, the CLI can use Docker Hub
with `SUPABASE_INTERNAL_IMAGE_REGISTRY=docker.io make supabase-up`.

Use the local Supabase database DSNs when developing against that stack. Keep
credentials in ignored local configuration and keep local services off public
interfaces. Tenant schema, policies, and the queue backend are separate slices.
