# Discovery analysis and evidence review

From a discovery session, open **Discovery analysis**. A workspace admin or the
assigned sales engineer can queue analysis on an active opportunity. Admins and
sales engineers in the workspace can read results. Each run pins the ready
transcript sources available at enqueue time. Summary sources stay separate.

Findings start as drafts. Open the quoted transcript segment to check that it
supports the statement. Confidence is the model's assessment. It does not
replace verification. Editing creates a draft revision with the existing
evidence anchors. Approval applies to the exact revision and records the
approver and time. If another reviewer saved a revision while you were editing,
reload before approving. Prior revisions and approvals remain available in the
database for audit.

## Provision the worker

Analysis is disabled by default. Create the worker login on the same Supabase
Postgres instance as the application **before** migrating to revision `0006`.
Run this as the database administrator and set the password through your normal
secret provisioning process. Grant it no application table roles.

```sql
CREATE ROLE demoforge_worker LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS;
```

Run `make migrate` using the separate migration credential. Revision `0006`
grants the worker login execute access to the restricted claim, evidence, failure,
and completion functions. The API continues to use the `demoforge_api` login.
Use separate runtime service environments for the API and worker.

| Setting | Scope |
| --- | --- |
| `DISCOVERY_PROVIDER=disabled` | Default. Controls whether the API can enqueue analysis. Existing runs remain reviewable. |
| `DISCOVERY_PROVIDER=openai` | API and worker. Enable only in an environment approved to send content to the provider. |
| `DISCOVERY_PROVIDER=fake` and `DISCOVERY_SYNTHETIC_DEV=true` | API and worker in disposable development and test environments. The UI labels these runs as synthetic. |
| `DISCOVERY_WORKER_DATABASE_URL` | Worker-only Postgres DSN for `demoforge_worker` including the SSL options required by the host. |
| `OPENAI_API_KEY` | Worker-only server secret for the OpenAI project. |

Run the independent worker process from the repository root:

```sh
PYTHONPATH=services/api:services/worker uv run --locked python -m demoforge_worker.discovery
```

The worker polls Postgres every two seconds when idle. On an interrupted
attempt, another worker can claim the persisted job after its 75-second lease
expires. The previous lease cannot publish results. Transient failures
automatically back off, up to three attempts total, including interrupted
attempts. Permanent errors publish no findings. Repeated starts on the same
source snapshot, provider, model, and prompt version return the existing run.
Import additional evidence or use a new session to start from different input.

Postgres is the durable queue for this workflow. The run and source snapshot
commit together, so dispatch needs no second broker write. The worker rechecks
the original requester's workspace role, opportunity ownership, and archive
state before reading transcript content and again before publishing. Claim
state and error metadata contain no transcript text, prompts, responses, or
secrets. Completion and validated findings commit together.

## Analysis bounds and privacy

- At most 600 segments and 30,000 input tokens under a conservative UTF-8
  byte bound, including prompt and schema framing. Oversized input fails
  before model dispatch.
- Up to 2,500 completion tokens and 25 findings per response. The configured
  OpenAI model is `gpt-4.1-mini-2025-04-14`. The preflight estimate caps one
  attempt at USD 0.016 and a run at USD 0.048 using the documented code rates.
  Review pricing when changing the model or rates.
- The workspace accepts up to 20 new runs in a rolling 24-hour period, with up
  to three active runs and one active run per session.
- Input text is serialized as untrusted data. The request supplies no tools
  and sets `store: false`. Local strict validation rejects fabricated segment
  IDs and mismatched quotes before persistence. Contradictions need at least
  two distinct verified spans. Inferences remain labeled. Source support for
  an asserted claim still requires human review.
- Real customer content remains gated on the privacy review, including the
  provider's applicable data handling and retention policies. The synthetic
  workflow and provider transport tests use no hosted credentials.

## Verify with synthetic data

1. Configure the fake provider on the API and worker in a disposable Supabase
   environment. Start the API, worker and web app.
2. Import a transcript containing `Synthetic pain: Audits are backlogged.`,
   two different lines that begin with `Synthetic volume:`, and a line
   instructing the model to invent a segment ID. Leave the budget unspecified.
3. Start analysis. Check that the status moves to **Complete** and that direct
   evidence, the contradictory volumes and the missing budget are labeled.
   Follow a quote link to the source.
4. Edit the statement and approve the new revision. Check that editing an
   approved finding creates a draft again. Open the run from another
   workspace and confirm that access is denied.

`make check` runs schema and OpenAI transport tests. The
[Supabase test runner](../tests/run_local_supabase.py) covers the real database,
worker and API flows, including repeat starts, abandoned leases, revoked
membership, fabricated citations, provider retries and approval conflicts.

## Rollback

If planning is deployed, complete its [rollback](PLANNING.md#setup-verification-and-rollback)
before downgrading analysis. Disable analysis in the API and stop the worker. Back up analysis jobs, source
snapshots, findings, evidence and approvals before downgrading. Run
`uv run --locked alembic downgrade 0005` with the migration credential. This
removes analysis history and worker grants. Revision `0005` preserves the
discovery sources and originals. Deploy the previous app revision and restore
any analysis history only after reapplying `0006`.
