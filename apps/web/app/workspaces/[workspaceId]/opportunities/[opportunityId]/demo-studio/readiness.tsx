"use client";

import { Check, Download, Minus } from "lucide-react";
import { useActionState } from "react";

import type { MappingParams } from "@/lib/catalog";
import type { PrepTask, Readiness } from "@/lib/storyboard-fields";

import { type Target, updatePreparation } from "./actions";

function PrepControl({ params, target, task, complete, label }: {
  params: MappingParams; target: Target; task: PrepTask; complete: boolean; label: string;
}) {
  const [state, submit, pending] = useActionState(updatePreparation.bind(null, params, target, task, !complete), {});
  const action = complete ? "Reopen" : "Mark complete";
  return (
    <form action={submit} className="space-y-1.5">
      <button aria-label={`${action}: ${label}`} className="button-secondary" type="submit" disabled={pending}>
        {pending ? "Saving…" : action}
      </button>
      {state.error && <p role="alert" className="text-xs text-danger">{state.error}</p>}
      {state.message && <p role="status" className="sr-only">{state.message}</p>}
    </form>
  );
}

export function ReadinessPanel({ params, target, readiness, canEdit, approved, studioHref }: {
  params: MappingParams; target: Target; readiness: Readiness; canEdit: boolean; approved: boolean; studioHref: string;
}) {
  const download = (format: "md" | "pdf") => `${studioHref}/export?${new URLSearchParams({
    storyboard: target.id, revision: String(target.revision), format,
  })}`;
  const completed = readiness.checks.filter((check) => check.complete).length;
  return (
    <section aria-labelledby="demo-readiness" className="opportunity-panel min-w-0 space-y-4 p-5 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="demo-readiness" className="text-lg font-semibold">Demo readiness</h2>
          <p className="text-sm text-muted-foreground">{completed} of {readiness.checks.length} checks complete</p>
        </div>
        <p role="status" className={`rounded-full border px-3 py-1 text-xs font-semibold ${readiness.ready ? "text-brand" : "text-danger"}`}>
          {readiness.ready ? "Demo-ready" : "Not demo-ready"}
        </p>
      </header>
      <ul aria-label="Readiness checklist" className="divide-y rounded-lg border">
        {readiness.checks.map((check) => (
          <li key={check.label} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
            <div className="flex min-w-0 items-start gap-2">
              {check.complete ? <Check size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-brand" /> : <Minus size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-muted-foreground" />}
              <span className="min-w-0 break-words"><span className="sr-only">{check.complete ? "Complete: " : "Incomplete: "}</span>{check.label}</span>
            </div>
            {canEdit && check.task && <PrepControl params={params} target={target} task={check.task} complete={check.complete} label={check.label} />}
          </li>
        ))}
      </ul>
      {!readiness.ready && <div className="rounded-lg border border-danger p-3 text-sm">
        <h3 className="font-semibold">Readiness blockers</h3>
        <ul className="mt-2 list-inside list-disc space-y-1 break-words text-muted-foreground">
          {readiness.checks.flatMap((check) => check.blocker ? [<li key={check.label}>{check.blocker}</li>] : [])}
        </ul>
      </div>}
      <div className="space-y-2 border-t pt-4">
        <h3 className="text-sm font-semibold">Export revision {target.revision}</h3>
        {approved ? <div className="flex flex-wrap gap-2">
          <a className="button-secondary" href={download("md")} download><Download size={15} aria-hidden="true" /> Download Markdown</a>
          <a className="button-secondary" href={download("pdf")} download><Download size={15} aria-hidden="true" /> Download PDF</a>
        </div> : <p className="text-sm text-muted-foreground">Approve this revision to download Markdown or PDF.</p>}
      </div>
    </section>
  );
}
