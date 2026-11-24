"use client";

import { useRouter } from "next/navigation";
import { startTransition, useActionState, useEffect } from "react";

import type { AnalysisParams, Finding } from "@/lib/analysis";

import { reviewFinding, startAnalysis } from "./actions";

export function RefreshWhileActive({ running }: { running: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => router.refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [router, running]);
  return null;
}

export function StartAnalysis({ params, disabled }: { params: AnalysisParams; disabled: boolean }) {
  const [state, action, pending] = useActionState(startAnalysis.bind(null, params), {});
  return (
    <form action={action} className="space-y-2">
      <button className="button-primary" disabled={pending || disabled}>
        {pending ? "Queueing…" : "Analyze transcript"}
      </button>
      {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
    </form>
  );
}

export function FindingEditor({
  params, finding, run,
}: { params: AnalysisParams; finding: Finding; run: string }) {
  const target = { run, finding: finding.id, revision: finding.revision };
  const [editState, edit, saving] = useActionState(
    reviewFinding.bind(null, params, "edit", target), {},
  );
  const [approval, approve, approving] = useActionState(
    reviewFinding.bind(null, params, "approve", target), {},
  );
  return (
    <div className="space-y-3 border-t pt-4">
      <details className="space-y-3">
        <summary className="cursor-pointer text-sm font-semibold text-brand">Edit finding</summary>
        <form onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          startTransition(() => edit(data));
        }} className="space-y-3">
          <label className="grid gap-2 text-sm">
            Statement
            <textarea className="opportunity-field" name="statement" required maxLength={800} defaultValue={finding.statement} />
          </label>
          <label className="grid gap-2 text-sm">
            Rationale
            <textarea className="opportunity-field" name="rationale" required maxLength={800} defaultValue={finding.rationale} />
          </label>
          {editState.error && <p role="alert" className="text-sm text-danger">{editState.error}</p>}
          <button className="button-secondary" disabled={saving || approving}>{saving ? "Saving…" : "Save as new draft"}</button>
        </form>
      </details>
      {finding.approved_at === null && (
        <form action={approve} className="space-y-2">
          <button className="button-primary" disabled={saving || approving}>
            {approving ? "Approving…" : "Approve this revision"}
          </button>
          {approval.error && <p role="alert" className="text-sm text-danger">{approval.error}</p>}
        </form>
      )}
    </div>
  );
}
