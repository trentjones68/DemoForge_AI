"use client";

import { startTransition, useActionState, useEffect, useRef } from "react";

import { type Capability, supportLabels } from "@/lib/catalog-fields";

import { addRelease, archiveCapability, type Result, saveCapability } from "./actions";

function Feedback({ state }: { state: Result }) {
  return <>
    {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
    {state.message && <p role="status" className="text-sm text-muted-foreground">{state.message}</p>}
  </>;
}

export function NewRelease({ workspace }: { workspace: string }) {
  const [state, action, pending] = useActionState(addRelease.bind(null, workspace), {});
  return (
    <details className="opportunity-panel space-y-3 p-5">
      <summary className="cursor-pointer font-semibold text-brand">Add product release</summary>
      <form action={action} className="space-y-3">
        <fieldset disabled={pending} className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm font-medium">Product
            <input name="product" className="opportunity-field" required maxLength={120} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Version
            <input name="version" className="opportunity-field" required maxLength={80} />
          </label>
        </fieldset>
        <Feedback state={state} />
        <button type="submit" className="button-primary" disabled={pending}>{pending ? "Saving…" : "Create release"}</button>
      </form>
    </details>
  );
}

export function EntryForm({ workspace, release, item }: { workspace: string; release: string; item?: Capability }) {
  const target = item ? { id: item.id, revision: item.revision } : null;
  const [state, action, saving] = useActionState(saveCapability.bind(null, workspace, release, target), {});
  const formRef = useRef<HTMLFormElement>(null);
  const creating = !item;
  useEffect(() => {
    if (creating && state.message) formRef.current?.reset();
  }, [creating, state]);
  const title = item ? "Edit capability" : "Add capability";
  return (
    <details className="space-y-3">
      <summary className="cursor-pointer font-semibold text-brand">{title}</summary>
      <form aria-label={title} ref={formRef} onSubmit={(event) => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        startTransition(() => action(fields));
      }} className="space-y-3">
        <fieldset disabled={saving} className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm font-medium">Capability name
            <input name="name" className="opportunity-field" required maxLength={120} defaultValue={item?.name} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Support status
            <select name="support_status" className="opportunity-field" defaultValue={item?.support_status ?? "unknown"}>
              {Object.entries(supportLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Description
            <textarea name="description" className="opportunity-field" required maxLength={800} defaultValue={item?.description} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Limitations
            <textarea name="limitations" className="opportunity-field" maxLength={800} defaultValue={item?.limitations} />
            <span className="text-xs text-muted-foreground">Required for partial and unsupported entries.</span>
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Integration dependencies
            <textarea name="dependencies" className="opportunity-field" defaultValue={item?.dependencies.join("\n")} />
            <span className="text-xs text-muted-foreground">Enter one dependency per line.</span>
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Exact requirement phrases
            <textarea name="match_phrases" className="opportunity-field" defaultValue={item?.match_phrases.join("\n")} />
            <span className="text-xs text-muted-foreground">Enter one whole requirement per line for automatic matching.</span>
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Document title
            <input name="source_title" className="opportunity-field" required maxLength={200} defaultValue={item?.source_title} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">Section or anchor
            <input name="source_locator" className="opportunity-field" required maxLength={200} defaultValue={item?.source_locator} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium sm:col-span-2">HTTPS documentation URL
            <input name="source_url" type="url" className="opportunity-field" required maxLength={1200} defaultValue={item?.source_url} />
          </label>
        </fieldset>
        <Feedback state={state} />
        <button type="submit" className="button-secondary" disabled={saving}>
          {saving ? "Saving…" : item ? "Save new revision" : "Create capability"}
        </button>
      </form>
    </details>
  );
}

export function ArchiveEntry({ workspace, release, item }: { workspace: string; release: string; item: Capability }) {
  const [state, action, pending] = useActionState(
    archiveCapability.bind(null, workspace, release, { id: item.id, revision: item.revision }), {},
  );
  return (
    <form action={action} className="space-y-2">
      <button type="submit" className="button-secondary" disabled={pending}>{pending ? "Archiving…" : "Archive capability"}</button>
      <Feedback state={state} />
    </form>
  );
}
