# Shared contracts

JSON Schema Draft 2020-12 files under `v1/` define the first wire contracts.
The API exposes the health response and the worker accepts only a reference to a
persisted job. Keep customer content and tenant authorization out of messages.

Update the schema, typed boundary, and contract tests together. Use a new
version for breaking changes. `make test` exercises the API and worker against
these schemas with synthetic inputs.
