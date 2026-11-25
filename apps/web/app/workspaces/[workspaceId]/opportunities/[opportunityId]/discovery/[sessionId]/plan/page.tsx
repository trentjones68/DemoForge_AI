import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import type { AnalysisParams } from "@/lib/analysis";
import { loadPlanningContext, readHistory, readPlan } from "@/lib/planning";
import { categoryLabels, gapStatusLabels } from "@/lib/planning-fields";

import { ApproveItem, GenerateDrafts, PlanForm } from "./controls";

export default async function PlanningPage({
  params, searchParams,
}: {
  params: Promise<AnalysisParams>;
  searchParams: Promise<{ history?: string }>;
}) {
  const identifiers = await params;
  const context = await loadPlanningContext(identifiers);
  const plan = await readPlan(context);
  const requested = (await searchParams).history;
  const historical = requested ? plan.items.find((item) => item.id === requested) : undefined;
  if (requested && !historical) notFound();
  const history = historical ? await readHistory(context, historical.id) : [];
  const requirements = plan.items.filter((item) => item.kind === "requirement");
  const gaps = plan.items.filter((item) => item.kind === "gap");
  const formContext = {
    params: identifiers,
    owners: plan.owners,
    userId: context.userId,
    requirements: requirements.map(({ id, statement }) => ({ id, statement })),
  };

  return (
    <div className="space-y-6">
      <Link href={context.sessionHref} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> Discovery session
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Requirements and gaps</h1>
          <p className="text-sm text-muted-foreground">Review requirements and follow-up questions before planning the demo.</p>
        </div>
        {context.canWrite && <GenerateDrafts params={identifiers} disabled={!plan.has_approved_insights} />}
      </header>
      {!plan.has_approved_insights && (
        <p className="opportunity-panel p-5 text-sm">
          <Link href={context.analysisHref} className="font-semibold text-brand hover:underline">Approve a discovery finding</Link> to generate drafts.
        </p>
      )}
      {historical && (
        <section id={`history-${historical.id}`} className="opportunity-panel scroll-mt-4 space-y-4 p-5" aria-label="Revision history">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h2 className="font-semibold">Revision history</h2>
            <Link href={`${context.planHref}#item-${historical.id}`} className="text-sm font-semibold text-brand hover:underline">
              Close history
            </Link>
          </div>
          {history.map((revision) => (
            <div key={revision.revision} id={`plan-${historical.id}-r${revision.revision}`} className="scroll-mt-4 space-y-2 border-t pt-3 text-sm">
              <p className="font-medium">Revision {revision.revision} · {revision.approved_at ? "Approved" : "Draft"}</p>
              <p className="whitespace-pre-wrap break-words">{revision.statement}</p>
              <p className="whitespace-pre-wrap break-words text-muted-foreground">{revision.rationale}</p>
              <p className="text-xs text-muted-foreground">
                {revision.priority} priority{revision.status ? ` · ${gapStatusLabels[revision.status]}` : ""}
                {revision.owner_id ? ` · Owner ${revision.owner_id}` : ""}
              </p>
              <p className="break-words text-xs text-muted-foreground">
                Edited by {revision.actor_id} · <time dateTime={revision.created_at}>{revision.created_at}</time>
                {revision.approved_by && ` · Approved by ${revision.approved_by} at ${revision.approved_at}`}
              </p>
            </div>
          ))}
        </section>
      )}
      <div className="grid items-start gap-6 xl:grid-cols-2">
        {[
          { kind: "requirement" as const, label: "Requirements", items: requirements },
          { kind: "gap" as const, label: "Follow-up questions", items: gaps },
        ].map(({ kind, label, items }) => (
          <section key={kind} className="min-w-0 space-y-4" aria-label={label}>
            <h2 className="text-xl font-semibold">{label}</h2>
            {context.canWrite && <div className="opportunity-panel p-5"><PlanForm {...formContext} kind={kind} /></div>}
            {!items.length && <p className="opportunity-panel p-5 text-sm text-muted-foreground">No {label.toLowerCase()} yet.</p>}
            {items.map((item) => (
              <article id={`item-${item.id}`} key={item.id} className="opportunity-panel scroll-mt-4 space-y-4 p-5">
                <div className="flex flex-wrap gap-2 text-xs font-medium">
                  <span className="rounded-full bg-accent px-2.5 py-1 capitalize text-accent-foreground">{item.priority} priority</span>
                  <span className="rounded-full border px-2.5 py-1">{categoryLabels[item.category]}</span>
                  <span className="rounded-full border px-2.5 py-1">
                    {item.stale_source ? "Source changed" : item.approved_at ? "Approved" : "Draft"} · Revision {item.revision}
                  </span>
                  {item.status && <span className="rounded-full border px-2.5 py-1">{gapStatusLabels[item.status]}</span>}
                </div>
                <div className="space-y-2">
                  <h3 className="whitespace-pre-wrap break-words font-semibold">{item.statement}</h3>
                  <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{item.rationale}</p>
                  <p className="break-words text-xs text-muted-foreground">
                    {item.source_revision ? `Source finding revision ${item.source_revision}`
                      : item.generated ? "Generated from gaps in approved discovery" : "Added manually"}
                  </p>
                </div>
                {item.kind === "gap" && (
                  <div className="space-y-2 text-sm">
                    <p className="break-words">
                      <span className="font-medium">Owner</span>{" "}
                      {item.owner_id === context.userId ? "You" : item.owner_id ?? "Unassigned"}
                    </p>
                    <p className="font-medium">Affected requirements</p>
                    {item.affected_requirement_ids.length ? (
                      <ul className="space-y-1">
                        {requirements.filter((entry) => item.affected_requirement_ids.includes(entry.id)).map((entry) => (
                          <li key={entry.id}>
                            <a className="break-words text-brand hover:underline" href={`#item-${entry.id}`}>{entry.statement}</a>
                          </li>
                        ))}
                      </ul>
                    ) : <p className="text-muted-foreground">None linked.</p>}
                  </div>
                )}
                {item.evidence.length > 0 && (
                  <ul className="space-y-2" aria-label="Transcript evidence">
                    {item.evidence.map((evidence, index) => (
                      <li key={`${evidence.segment_id}-${index}`} className="space-y-1 rounded-lg border p-3">
                        <blockquote className="whitespace-pre-wrap break-words text-sm">{evidence.quote}</blockquote>
                        <Link className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline"
                          href={`${context.sessionHref}?source=${evidence.source_id}&page=${evidence.page}#segment-${evidence.segment_id}`}>
                          Open transcript segment <ExternalLink size={14} aria-hidden="true" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                <Link href={`${context.planHref}?history=${item.id}#history-${item.id}`} className="text-sm font-semibold text-brand hover:underline">
                  Revision history
                </Link>
                {context.canWrite && (
                  <div className="space-y-3 border-t pt-3">
                    <PlanForm key={`${item.revision}`} {...formContext} kind={kind} item={item} />
                    {!item.approved_at && !item.stale_source && <ApproveItem params={identifiers} item={item} />}
                  </div>
                )}
              </article>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
