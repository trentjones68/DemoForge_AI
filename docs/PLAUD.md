# Plaud imports and automation verification

The supplied PRD, architecture, and build prompts establish a manual import
baseline. The architecture's proposed fields describe DemoForge's intended
input. The supplied material contains no Plaud or intermediary documentation
that establishes an external integration contract. [PRD](01_PRD.md) · [Architecture](02_ARCHITECTURE.md#plaud-ingestion-contract) · [Prompt 10](03_BUILD_PROMPTS.md#prompt-10--plaud-automation-adapter-conditional)

| Contract area | Evidence needed before enabling automation |
| --- | --- |
| Availability | Officially supported trigger or export method, plan and region eligibility, and the intended account's access |
| Delivery | Event name and semantics, and whether it delivers a transcript, summary, or file |
| Authentication | Sender identity, signature or other authenticated delivery mechanism, and a verified workspace binding |
| Replay and recovery | Stable event identity, timestamps, retry behavior, deduplication scope, and provider limits |
| Data handling | Customer authorization and data transfer terms, plus sanitized evidence from a sandbox delivery and retry |

Automation remains disabled. DemoForge accepts an authenticated, user-initiated
file upload or JSON import. The `plaud` provenance value records the caller's
attribution to a manual Plaud export. [Verification gate](DECISIONS.md#d6-verify-plaud-before-enabling-automation)

## Manual export workflow

1. Confirm permission to use the recording and import its contents. Obtain the
   transcript through a manual export or text copy available in your Plaud
   account. Use TXT, Markdown, DOCX, or a PDF with selectable text when
   available. Keep any speaker labels and timestamps in the exported text.
2. Sign in to DemoForge, open the opportunity, and open or create a discovery
   session. Choose **Plaud export** as the provenance. Select **Transcript**
   and upload the original file or paste the transcript. Confirm recording and
   import consent and submit.
3. If you have a summary, import it separately as **Summary**. Verify each
   source's provenance and segment links in the viewer. Use the original
   download if you need to verify the bytes against the submitted file.

## Authenticated JSON import

Send `POST /v1/workspaces/{workspace_id}/opportunities/{opportunity_id}/discovery/{session_id}/imports`
with `Authorization: Bearer <Supabase user access token>`, `Content-Type: application/json`,
and `X-Import-Consent: true`. Workspace admins and the assigned sales engineer
can import into an existing session on an active opportunity. The API checks
workspace membership and the session's parent opportunity server-side. Use
server-side credential handling if calling from an internal client.

```json
{
  "kind": "transcript",
  "provider": "plaud",
  "text": "[00:00:12] Analyst: Review the fictional audit totals."
}
```

The `kind` is `transcript` or `summary`. The optional `provider` defaults to
`manual`. Send plain text as a JSON string, up to 250,000 Unicode code points.
The JSON body limit is 3,001,024 bytes, including escaping and field names.
For files, use the existing authenticated **Plaud export** upload in DemoForge.
The same [parsing, storage, and quota limits](DISCOVERY.md#limits-and-recovery)
apply. [Request schema](../packages/contracts/v1/discovery-text-import.schema.json)

- `201` returns `{ "source": { ... }, "duplicate": false }` after the source
  is ready. Retrieve its segments from `GET .../sources/{source_id}/segments`.
- `200` returns the existing source with `duplicate: true` when the decoded
  text has the same UTF-8 bytes and source kind in the same workspace and
  session. The first import keeps its attribution. The JSON, paste, and file
  paths share deduplication.
- For a temporary Storage failure or a lost response, retry the exact same
  text, kind, and session with bounded backoff. The database reservation lets
  the retry reuse the original object and publish once. `429` indicates the
  API is busy. Correct input, permission, quota, or consent errors before
  retrying. The private original and its import event are recorded through the
  existing discovery pipeline. The audit event contains identifiers and actor
  metadata.

The fallback uses the existing discovery database revision and Storage
settings. The disposable Supabase integration suite checks authentication,
workspace and opportunity isolation, consent, size limits, original replay,
source provenance, and the single successful import audit event.
