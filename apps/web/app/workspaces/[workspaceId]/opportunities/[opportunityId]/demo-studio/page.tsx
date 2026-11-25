import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { releases, type MappingParams } from "@/lib/catalog";
import { revisionNumber, uuid } from "@/lib/storyboard-fields";
import { storyboard, storyboards, studioContext } from "@/lib/storyboards";

import { AgendaControls, ApprovalControl, GenerateForm, SceneControls } from "./controls";
import { CopyDetails, EvidenceDetails } from "./scene-content";

const revisionNames = {
  generated: "Generated", scene_edited: "Scene edited", agenda_updated: "Agenda updated", scene_regenerated: "Scene regenerated",
};

export default async function DemoStudio({ params, searchParams }: {
  params: Promise<MappingParams>;
  searchParams: Promise<{ storyboard?: string; revision?: string }>;
}) {
  const { workspaceId, opportunityId } = await params;
  const context = await studioContext(workspaceId, opportunityId);
  const query = await searchParams;
  const selected = z.object({ storyboard: uuid.optional(), revision: z.coerce.number().pipe(revisionNumber).optional() }).safeParse({
    storyboard: query.storyboard, revision: query.revision,
  });
  if (!selected.success) notFound();
  const [boards, products] = await Promise.all([storyboards(context), releases(context)]);
  const id = selected.data.storyboard ?? boards[0]?.id;
  const studio = id ? await storyboard(context, id, selected.data.revision) : null;
  const board = studio?.storyboard;
  const current = !!board && board.revision === studio.current_revision;
  const canEdit = context.canWrite && current;
  const stale = board?.scenes.some((scene) => scene.stale_evidence) ?? false;
  const hasWarnings = board?.scenes.some((scene) => scene.support_warning !== null) ?? false;
  const boardHref = (storyboardId: string, revision?: number) => `${context.studioHref}?${new URLSearchParams({
    storyboard: storyboardId, ...(revision ? { revision: String(revision) } : {}),
  })}`;

  return (
    <div className="space-y-6">
      <Link href={context.opportunityHref} className="text-sm font-semibold text-brand hover:underline">Opportunity</Link>
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Demo Studio</h1>
        <p className="text-sm text-muted-foreground">Plan a timed demo around approved requirements and reviewed product evidence.</p>
      </header>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,3fr)]">
        <aside aria-label="Storyboards" className="space-y-4">
          <section className="opportunity-panel space-y-3 p-4">
            <h2 className="font-semibold">Storyboards</h2>
            {boards.length ? <ul className="space-y-1 text-sm">{boards.map((item) => <li key={item.id}>
              <Link href={boardHref(item.id)} aria-current={item.id === id ? "true" : undefined}
                className={`block break-words rounded-lg px-3 py-2 hover:bg-accent ${item.id === id ? "bg-accent font-semibold" : ""}`}>
                {item.audience}<span className="block text-xs text-muted-foreground">{item.release.product} · {item.release.version}</span>
              </Link>
            </li>)}</ul> : <p className="text-sm text-muted-foreground">No storyboards yet.</p>}
          </section>
          {studio && board && <section className="opportunity-panel space-y-3 p-4">
            <h2 className="font-semibold">Revision history</h2>
            <ol className="max-h-72 space-y-1 overflow-y-auto text-sm" reversed>
              {studio.revisions.map((item) => <li key={item.revision}>
                <Link href={boardHref(board.id, item.revision === studio.current_revision ? undefined : item.revision)}
                  aria-current={item.revision === board.revision ? "true" : undefined}
                  className={`block rounded-lg px-3 py-2 hover:bg-accent ${item.revision === board.revision ? "bg-accent font-semibold" : ""}`}>
                  Revision {item.revision} · {item.approved_at ? "Approved" : "Draft"}
                  <span className="block text-xs text-muted-foreground">{revisionNames[item.action]}</span>
                </Link>
              </li>)}
            </ol>
          </section>}
        </aside>
        <div className="min-w-0 space-y-5">
          {context.canWrite && products.length > 0 && (
            <details open={!board} className="opportunity-panel space-y-4 p-5">
              <summary className="cursor-pointer font-semibold text-brand">New storyboard</summary>
              <p className="text-sm text-muted-foreground">Review a capability mapping for every approved requirement in the selected release.</p>
              <Link href={context.mappingHref} className="inline-block text-sm font-semibold text-brand hover:underline">Review capability mappings</Link>
              <GenerateForm key={board?.id ?? "new"} params={context.params} releases={products} />
            </details>
          )}
          {!board && context.canWrite && !products.length && (
            <p className="opportunity-panel p-5 text-sm">Add a release in the <Link href={`/workspaces/${workspaceId}/catalog`} className="font-semibold text-brand hover:underline">product capability catalog</Link> to get started.</p>
          )}
          {board && <>
            <section aria-label="Storyboard brief" className="opportunity-panel min-w-0 space-y-3 p-5 sm:p-6">
              <div className="flex flex-wrap gap-2 text-xs font-medium">
                <span className="rounded-full bg-accent px-2.5 py-1 text-accent-foreground">{board.approved_at ? "Approved" : "Draft"} · Revision {board.revision}</span>
                <span className="rounded-full border px-2.5 py-1">{board.brief.target_minutes} minutes</span>
                {!current && <span className="rounded-full border px-2.5 py-1">Historical revision</span>}
              </div>
              <h2 className="break-words text-2xl font-semibold">{board.brief.audience}</h2>
              <p className="break-words text-sm text-muted-foreground">{board.release.product} · {board.release.version}</p>
              <p className="text-sm font-semibold">Business outcomes</p>
              <ul className="list-inside list-disc space-y-1 break-words text-sm">{board.brief.business_outcomes.map((outcome, index) => <li key={index}>{outcome}</li>)}</ul>
              <p className="break-words text-xs text-muted-foreground">
                Edited by {board.actor_id} · <time dateTime={board.created_at}>{board.created_at}</time>
                {board.approved_at && <> · Approved by {board.approved_by} · <time dateTime={board.approved_at}>{board.approved_at}</time></>}
              </p>
              {stale && <p role="status" className="rounded-lg border border-danger p-3 text-sm font-medium">Some requirement or mapping revisions are stale. Review the current mappings and regenerate the affected scenes before approval.</p>}
            </section>
            {canEdit && <AgendaControls key={`${board.id}:${board.revision}`} params={context.params} board={board} />}
            <section aria-label="Storyboard scenes" className="space-y-4">
              {board.scenes.map((scene, index) => <article key={scene.id} className="opportunity-panel min-w-0 space-y-4 p-5 sm:p-6">
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground">Scene {index + 1} · {scene.minutes} min{scene.stale_evidence ? " · Stale evidence" : ""}</p>
                  <h3 className="break-words text-lg font-semibold">{scene.content.title}</h3>
                </div>
                {scene.support_warning && <p className="rounded-lg border border-danger p-3 text-sm font-medium">{scene.support_warning}</p>}
                <CopyDetails copy={scene.content} discussion={scene.support_warning !== null || scene.stale_evidence} />
                <EvidenceDetails scene={scene} discovery={context.href} mapping={context.mappingHref} release={board.release.id} />
                {canEdit && <SceneControls key={`${board.id}:${board.revision}:${scene.id}`} params={context.params}
                  target={{ id: board.id, revision: board.revision }} scene={scene}
                  provenance={{ discovery: context.href, mapping: context.mappingHref, release: board.release.id }} />}
              </article>)}
            </section>
            {canEdit && !stale && !board.approved_at && <section aria-label="Storyboard approval" className="opportunity-panel space-y-3 p-5">
              <h2 className="font-semibold">Approve storyboard revision {board.revision}</h2>
              <ApprovalControl key={`${board.id}:${board.revision}`} params={context.params} target={{ id: board.id, revision: board.revision }} hasWarnings={hasWarnings} />
            </section>}
          </>}
        </div>
      </div>
    </div>
  );
}
