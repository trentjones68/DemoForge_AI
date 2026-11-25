# Shared contracts

JSON Schema Draft 2020-12 files under `v1/` define the first wire contracts.
The API exposes the health response and the worker accepts only a reference to a
persisted job. Keep customer content and tenant authorization out of messages.
`storyboard.schema.json` is the Pydantic serialization schema for an exact
storyboard revision. The API and database also validate total duration and the
provenance relationships at runtime.
`storyboard-readiness.schema.json` defines the corresponding readiness summary
and revision-scoped preparation checks.
`discovery-text-import.schema.json` defines the request for importing transcript
or summary text into an authorized, existing discovery session.

Update the schema, typed boundary, and contract tests together. Use a new
version for breaking changes. `make test` exercises the API and worker against
these schemas with synthetic inputs.
