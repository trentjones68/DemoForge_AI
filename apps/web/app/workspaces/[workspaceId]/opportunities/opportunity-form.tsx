"use client";

import Link from "next/link";
import { useActionState } from "react";

import { ownerLabel, stageLabels, type Opportunity, type OpportunityInput } from "@/lib/opportunity-fields";

import { archiveOpportunity, saveOpportunity } from "./actions";

export function OpportunityForm({
  workspaceId, base, userId, owners, opportunity,
}: {
  workspaceId: string;
  base: string;
  userId: string;
  owners: string[];
  opportunity?: Opportunity;
}) {
  const [state, action, pending] = useActionState(
    saveOpportunity.bind(null, workspaceId, opportunity?.id ?? null, opportunity?.version ?? null),
    { message: "" },
  );
  const defaults = state.values ?? opportunity;

  function fieldProps(name: keyof OpportunityInput) {
    return {
      id: name,
      name,
      className: "opportunity-field",
      "aria-invalid": !!state.errors?.[name],
      "aria-describedby": state.errors?.[name] ? `${name}-error` : undefined,
    };
  }

  function error(name: keyof OpportunityInput) {
    return state.errors?.[name] && (
      <span id={`${name}-error`} className="text-sm font-medium text-danger">{state.errors[name]?.[0]}</span>
    );
  }

  return (
    <form action={action} className="opportunity-panel max-w-3xl space-y-6 p-5 sm:p-8">
      {state.message && <p role="alert" className="rounded-lg bg-danger-background p-3 text-sm text-danger">{state.message}</p>}
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="grid gap-2 text-sm font-medium">
          Opportunity name
          <input {...fieldProps("name")} required maxLength={120} defaultValue={defaults?.name} />
          {error("name")}
        </label>
        <label className="grid gap-2 text-sm font-medium">
          Company
          <input {...fieldProps("company")} required maxLength={120} defaultValue={defaults?.company} />
          {error("company")}
        </label>
        <label className="grid gap-2 text-sm font-medium">
          Product interest
          <input {...fieldProps("product")} required maxLength={120} defaultValue={defaults?.product} />
          {error("product")}
        </label>
        <label className="grid gap-2 text-sm font-medium">
          Stage
          <select {...fieldProps("stage")} defaultValue={defaults?.stage ?? "discovery"}>
            {Object.entries(stageLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          {error("stage")}
        </label>
        <label className="grid gap-2 text-sm font-medium">
          Target demo date
          <input {...fieldProps("demo_date")} type="date" max="9999-12-31" defaultValue={defaults?.demo_date ?? ""} />
          {error("demo_date")}
        </label>
        {owners.length > 0 && (
          <label className="grid gap-2 text-sm font-medium">
            Owner
            <select {...fieldProps("owner_id")} defaultValue={defaults?.owner_id ?? ""}>
              <option value="">{opportunity ? "Keep current owner" : "You (default)"}</option>
              {owners.map((id) => <option key={id} value={id}>{ownerLabel(id, userId)}</option>)}
            </select>
            {error("owner_id")}
          </label>
        )}
      </div>
      <label className="grid gap-2 text-sm font-medium">
        Primary use case
        <textarea {...fieldProps("use_case")} rows={2} maxLength={300} defaultValue={defaults?.use_case} />
        {error("use_case")}
      </label>
      <label className="grid gap-2 text-sm font-medium">
        Notes
        <textarea {...fieldProps("notes")} rows={5} maxLength={5000} defaultValue={defaults?.notes} />
        {error("notes")}
      </label>
      <div className="flex flex-wrap gap-3 border-t pt-5">
        <button type="submit" className="button-primary" disabled={pending}>
          {pending ? "Saving…" : opportunity ? "Save changes" : "Create opportunity"}
        </button>
        <Link href={opportunity ? `${base}/${opportunity.id}` : base} className="button-secondary">Cancel</Link>
      </div>
    </form>
  );
}

export function ArchiveForm({ workspaceId, opportunity }: { workspaceId: string; opportunity: Opportunity }) {
  const [state, action, pending] = useActionState(
    archiveOpportunity.bind(null, workspaceId, opportunity.id, opportunity.version),
    { message: "" },
  );
  return (
    <details className="opportunity-panel p-4">
      <summary className="cursor-pointer font-semibold text-danger">Archive opportunity</summary>
      <p className="mt-3 text-sm text-muted-foreground">This moves the opportunity to the archived list and makes it read only.</p>
      <form action={action} className="mt-3 space-y-3">
        {state.message && <p role="alert" className="text-sm text-danger">{state.message}</p>}
        <button type="submit" className="button-secondary text-danger" disabled={pending}>
          {pending ? "Archiving…" : "Confirm archive"}
        </button>
      </form>
    </details>
  );
}
