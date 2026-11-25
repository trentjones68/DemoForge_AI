"use client";

import { startTransition, useActionState } from "react";

import type { Mapping, MappingParams } from "@/lib/catalog";
import { type Capability, supportLabels } from "@/lib/catalog-fields";

import { generateMappings, type Result, reviewMapping, updateMapping } from "./actions";

function Feedback({ state }: { state: Result }) {
  return <>
    {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
    {state.message && <p role="status" className="text-sm text-muted-foreground">{state.message}</p>}
  </>;
}

export function GenerateMappings({ params, release, disabled }: { params: MappingParams; release: string; disabled: boolean }) {
  const [state, action, pending] = useActionState(generateMappings.bind(null, params, release), {});
  return (
    <form action={action} className="space-y-2">
      <button type="submit" className="button-primary" disabled={disabled || pending}>{pending ? "Generating…" : "Generate mapping drafts"}</button>
      <Feedback state={state} />
    </form>
  );
}

function choice(item: Capability) {
  return `${item.id}:${item.revision}`;
}

export function MappingControls({ params, release, item, entries }: {
  params: MappingParams; release: string; item: Mapping; entries: Capability[];
}) {
  const target = { id: item.id, revision: item.revision };
  const [editState, update, saving] = useActionState(updateMapping.bind(null, params, release, target), {});
  const [reviewState, review, reviewing] = useActionState(reviewMapping.bind(null, params, release, target), {});
  const value = item.capability ? choice(item.capability) : "";
  return (
    <div className="space-y-3 border-t pt-4">
      <details className="space-y-3">
        <summary className="cursor-pointer font-semibold text-brand">Edit mapping</summary>
        <form onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          startTransition(() => update(data));
        }} className="space-y-3">
          <fieldset disabled={saving || reviewing} className="space-y-3">
            <label className="grid gap-1.5 text-sm font-medium">Catalog evidence
              <select className="opportunity-field" name="evidence" defaultValue={value}>
                <option value="">No matching evidence (unknown)</option>
                {item.stale_evidence && value && <option value={value} disabled>Previous revision · select current evidence</option>}
                {entries.map((entry) => (
                  <option key={entry.id} value={choice(entry)}>
                    {entry.name} · {supportLabels[entry.support_status]} · r{entry.revision}
                  </option>
                ))}
              </select>
              <span className="text-xs text-muted-foreground">Support depends on a documented exact requirement phrase.</span>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">Mapping rationale
              <textarea className="opportunity-field" name="rationale" maxLength={800} required defaultValue={item.rationale} />
            </label>
          </fieldset>
          <Feedback state={editState} />
          <button type="submit" className="button-secondary" disabled={saving || reviewing}>
            {saving ? "Saving…" : "Save mapping draft"}
          </button>
        </form>
      </details>
      {(!item.reviewed_at && !item.stale_evidence) && (
        <form action={review} className="space-y-2">
          <button type="submit" className="button-primary" disabled={reviewing || saving}>
            {reviewing ? "Reviewing…" : "Confirm this mapping revision"}
          </button>
          <Feedback state={reviewState} />
        </form>
      )}
    </div>
  );
}
