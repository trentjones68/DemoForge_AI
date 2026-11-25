import { ArrowLeft, Building2, FileText, Pencil } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { formatDemoDate, ownerLabel, stageLabels } from "@/lib/opportunity-fields";
import { canEdit, loadOpportunity, loadOpportunityContext } from "@/lib/opportunities";

import { ArchiveForm } from "../opportunity-form";

export default async function OpportunityDetail({
  params,
}: {
  params: Promise<{ workspaceId: string; opportunityId: string }>;
}) {
  const { workspaceId, opportunityId } = await params;
  const context = await loadOpportunityContext(workspaceId);
  const item = await loadOpportunity(context, opportunityId);
  const editable = canEdit(context, item);

  return (
    <div className="space-y-6">
      <Link href={context.base} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> Opportunities
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground">{stageLabels[item.stage]}</span>
            {item.archived_at && <span className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground">Archived · Read only</span>}
          </div>
          <h1 className="break-words text-3xl font-semibold tracking-tight sm:text-4xl">{item.name}</h1>
          <p className="flex items-start gap-2 break-words text-muted-foreground"><Building2 size={17} className="mt-0.5 shrink-0" aria-hidden="true" /><span className="min-w-0 break-words">{item.company}</span></p>
        </div>
        {editable && <Link href={`${context.base}/${item.id}/edit`} className="button-primary"><Pencil size={15} aria-hidden="true" /> Edit opportunity</Link>}
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="opportunity-panel min-w-0 divide-y">
          <section className="space-y-2 p-5 sm:p-6" aria-labelledby="use-case">
            <h2 id="use-case" className="font-semibold">Primary use case</h2>
            <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{item.use_case || "No use case added."}</p>
          </section>
          <section className="space-y-2 p-5 sm:p-6" aria-labelledby="opportunity-notes">
            <h2 id="opportunity-notes" className="font-semibold">Notes</h2>
            <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{item.notes || "No notes added."}</p>
          </section>
        </div>
        <div className="space-y-4">
          <dl className="opportunity-panel grid gap-4 p-5">
            <Field label="Product interest">{item.product}</Field>
            <Field label="Target demo date">{formatDemoDate(item.demo_date)}</Field>
            <Field label="Owner"><span title={item.owner_id ?? undefined}>{ownerLabel(item.owner_id, context.userId)}</span></Field>
          </dl>
          {(context.workspace.role === "admin" || context.workspace.role === "sales_engineer") && (
            <>
              <Link href={`${context.base}/${item.id}/discovery`} className="button-secondary w-full">
                <FileText size={16} aria-hidden="true" /> Discovery sessions
              </Link>
              <Link href={`${context.base}/${item.id}/capability-mappings`} className="button-secondary w-full">
                Capability mapping
              </Link>
              <Link href={`${context.base}/${item.id}/demo-studio`} className="button-secondary w-full">
                Demo Studio
              </Link>
            </>
          )}
          {editable && <ArchiveForm workspaceId={workspaceId} opportunity={item} />}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm font-semibold">{children}</dd></div>;
}
