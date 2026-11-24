"use client";

import { startTransition, useActionState, useEffect, useRef } from "react";

import type { AnalysisParams } from "@/lib/analysis";
import type { PlanItem } from "@/lib/planning";
import { categoryLabels, gapStatusLabels, type PlanningKind } from "@/lib/planning-fields";

import { type ActionState, approveItem, generateDrafts, saveItem } from "./actions";

function Feedback({ state }: { state: ActionState }) {
  return (
    <>
      {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
      {state.message && <p role="status" className="text-sm text-muted-foreground">{state.message}</p>}
    </>
  );
}

export function GenerateDrafts({ params, disabled }: { params: AnalysisParams; disabled: boolean }) {
  const [state, action, pending] = useActionState(generateDrafts.bind(null, params), {});
  return (
    <form action={action} className="space-y-2">
      <button type="submit" className="button-primary" disabled={disabled || pending}>
        {pending ? "Generating…" : "Generate drafts"}
      </button>
      <Feedback state={state} />
    </form>
  );
}

export function PlanForm({
  params, kind, item, owners, userId, requirements,
}: {
  params: AnalysisParams;
  kind: PlanningKind;
  item?: PlanItem;
  owners: string[];
  userId: string;
  requirements: Pick<PlanItem, "id" | "statement">[];
}) {
  const target = item ? { id: item.id, revision: item.revision } : null;
  const [state, action, saving] = useActionState(saveItem.bind(null, params, kind, target), {});
  const formRef = useRef<HTMLFormElement>(null);
  const created = !item;
  useEffect(() => {
    if (created && state.message) formRef.current?.reset();
  }, [created, state]);
  const title = item ? "Edit item" : kind === "gap" ? "Add gap" : "Add requirement";
  const formerOwner = item?.owner_id && !owners.includes(item.owner_id) ? item.owner_id : null;

  return (
    <details className="space-y-3">
      <summary className="cursor-pointer text-sm font-semibold text-brand">{title}</summary>
      <form aria-label={title} ref={formRef} onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        startTransition(() => action(values));
      }} className="mt-3 space-y-3">
        <fieldset disabled={saving} className="space-y-3">
          <label className="grid gap-1.5 text-sm font-medium">
            {kind === "gap" ? "Question" : "Requirement"}
            <textarea name="statement" className="opportunity-field" maxLength={800} required defaultValue={item?.statement} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Rationale
            <textarea name="rationale" className="opportunity-field" maxLength={800} required defaultValue={item?.rationale} />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium">
              Category
              <select name="category" className="opportunity-field" defaultValue={item?.category ?? "general"}>
                {Object.entries(categoryLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </label>
            <label className="grid gap-1.5 text-sm font-medium">
              Priority
              <select name="priority" className="opportunity-field" defaultValue={item?.priority ?? "medium"}>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </label>
          </div>
          {kind === "gap" && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1.5 text-sm font-medium">
                  Owner
                  <select name="owner_id" className="opportunity-field" defaultValue={item?.owner_id ?? ""}>
                    <option value="">Unassigned</option>
                    {formerOwner && <option value={formerOwner}>Former workspace member</option>}
                    {owners.map((owner) => (
                      <option key={owner} value={owner}>{owner === userId ? "You" : owner}</option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1.5 text-sm font-medium">
                  Status
                  <select name="status" className="opportunity-field" defaultValue={item?.status ?? "open"}>
                    {Object.entries(gapStatusLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                </label>
              </div>
              {requirements.length > 0 && (
                <fieldset className="space-y-2 rounded-lg border p-3">
                  <legend className="px-1 text-sm font-medium">Affected requirements</legend>
                  {requirements.map((requirement) => (
                    <label key={requirement.id} className="flex items-start gap-2 text-sm">
                      <input className="mt-0.5 size-4 shrink-0 accent-brand" type="checkbox"
                        name="affected_requirements" value={requirement.id}
                        defaultChecked={item?.affected_requirement_ids.includes(requirement.id)} />
                      <span className="break-words">{requirement.statement}</span>
                    </label>
                  ))}
                </fieldset>
              )}
            </>
          )}
          <Feedback state={state} />
          <button type="submit" className="button-secondary">
            {saving ? "Saving…" : item ? "Save as new draft" : title}
          </button>
        </fieldset>
      </form>
    </details>
  );
}

export function ApproveItem({ params, item }: { params: AnalysisParams; item: PlanItem }) {
  const [state, action, pending] = useActionState(
    approveItem.bind(null, params, { id: item.id, revision: item.revision }), {},
  );
  return (
    <form action={action} className="space-y-2">
      <button type="submit" className="button-primary" disabled={pending}>
        {pending ? "Approving…" : "Approve this revision"}
      </button>
      <Feedback state={state} />
    </form>
  );
}
