"use client";

import { startTransition, useActionState, useId, useState } from "react";

import { createSession, importSource } from "./actions";

export function SessionForm({ workspaceId, opportunityId }: { workspaceId: string; opportunityId: string }) {
  const [state, action, pending] = useActionState(createSession.bind(null, workspaceId, opportunityId), {});
  return (
    <form onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      startTransition(() => action(values));
    }} className="opportunity-panel space-y-4 p-5 sm:p-6">
      <h2 className="font-semibold">New discovery session</h2>
      <fieldset disabled={pending} className="space-y-4">
        <label className="grid gap-1.5 text-sm font-medium">
          Session title
          <input name="title" className="opportunity-field" maxLength={120} required />
        </label>
        <label className="grid gap-1.5 text-sm font-medium">
          Meeting date (optional)
          <input name="occurred_on" type="date" className="opportunity-field" />
        </label>
        {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
        <button className="button-primary" type="submit">{pending ? "Creating…" : "Create session"}</button>
      </fieldset>
    </form>
  );
}

export function ImportForm({
  workspaceId, opportunityId, sessionId,
}: { workspaceId: string; opportunityId: string; sessionId: string }) {
  const consentHelpId = useId();
  const [method, setMethod] = useState("paste");
  const [state, action, pending] = useActionState(
    importSource.bind(null, workspaceId, opportunityId, sessionId), {},
  );
  return (
    <form onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      startTransition(() => action(values));
    }} className="opportunity-panel space-y-4 p-5 sm:p-6">
      <h2 className="font-semibold">Import source</h2>
      <fieldset disabled={pending} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm font-medium">
            Source type
            <select className="opportunity-field" name="kind">
              <option value="transcript">Transcript</option>
              <option value="summary">Summary</option>
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Provenance
            <select className="opportunity-field" name="provider">
              <option value="manual">Manual import</option>
              <option value="plaud">Plaud export</option>
            </select>
          </label>
        </div>
        <label className="grid gap-1.5 text-sm font-medium">
          Import method
          <select className="opportunity-field" name="method" value={method} onChange={(event) => setMethod(event.target.value)}>
            <option value="paste">Paste text</option>
            <option value="file">Upload file</option>
          </select>
        </label>
        {method === "paste" ? (
          <label className="grid gap-1.5 text-sm font-medium">
            Source text
            <textarea name="transcript" rows={7} maxLength={500000} required className="opportunity-field" />
          </label>
        ) : (
          <label className="grid gap-1.5 text-sm font-medium">
            Source file
            <input type="file" name="file" accept=".txt,.md,.docx,.pdf" required className="opportunity-field" />
            <span className="text-xs font-normal text-muted-foreground">TXT, Markdown, DOCX or PDF with selectable text. Up to 2 MiB.</span>
          </label>
        )}
        <div className="space-y-1.5">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" name="consent" required aria-describedby={consentHelpId}
              className="mt-0.5 h-4 w-4 shrink-0 accent-brand" />
            <span>I confirm I have permission to use this source and import it into this workspace.</span>
          </label>
          <p id={consentHelpId} className="pl-6 text-xs text-muted-foreground">
            Obtain any required recording consent before import. Use synthetic content in staging.
          </p>
        </div>
        {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
        <button type="submit" className="button-primary">{pending ? "Importing…" : "Import source"}</button>
      </fieldset>
    </form>
  );
}
