import Link from "next/link";
import { notFound } from "next/navigation";

import { CatalogEvidence, ReleaseSelect } from "@/app/workspaces/[workspaceId]/catalog/evidence";
import { loadMappingBoard, mappingContext, type MappingParams, releases } from "@/lib/catalog";
import { supportLabels } from "@/lib/catalog-fields";

import { GenerateMappings, MappingControls } from "./controls";

export default async function CapabilityMappings({
  params, searchParams,
}: {
  params: Promise<MappingParams>;
  searchParams: Promise<{ release?: string }>;
}) {
  const identifiers = await params;
  const context = await mappingContext(identifiers);
  const products = await releases(context);
  const selection = (await searchParams).release;
  const selected = selection ? products.find((entry) => entry.id === selection) : products[0];
  if (selection && !selected) notFound();
  const board = selected ? await loadMappingBoard(context, selected.id) : null;
  const perRequirement = new Map(board?.mappings.map((item) => [`${item.session_id}:${item.requirement_id}`, item]));

  return (
    <div className="space-y-6">
      <Link href={context.opportunityHref} className="text-sm font-semibold text-brand hover:underline">Opportunity</Link>
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Capability mapping</h1>
        <p className="text-sm text-muted-foreground">Review product support for approved requirements against a specific release.</p>
      </header>
      {board ? (
        <>
          <div className="opportunity-panel flex flex-wrap items-end justify-between gap-4 p-5">
            <form method="get" className="flex flex-wrap items-end gap-3">
              <ReleaseSelect entries={products} selected={board.release.id} />
              <button type="submit" className="button-secondary">View mappings</button>
            </form>
            {context.canWrite && <GenerateMappings key={board.release.id} params={identifiers}
              release={board.release.id} disabled={!board.requirements.length} />}
          </div>
          <section aria-label="Mapping review" className="space-y-4">
            {board.requirements.length === 0 && (
              <p className="opportunity-panel p-5 text-sm">
                <Link className="font-semibold text-brand hover:underline" href={context.href}>Approve requirements in discovery</Link> to begin mapping.
              </p>
            )}
            {board.requirements.map((requirement) => {
              const item = perRequirement.get(`${requirement.session_id}:${requirement.id}`);
              return (
                <article key={`${requirement.session_id}:${requirement.id}`} className="opportunity-panel min-w-0 space-y-4 p-5">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2 text-xs font-medium">
                      <span className="rounded-full border px-2.5 py-1">Requirement r{requirement.revision}</span>
                      {item && <span className="rounded-full bg-accent px-2.5 py-1 text-accent-foreground">
                        {item.stale_evidence ? "Stale catalog evidence" : supportLabels[item.support_status]}
                      </span>}
                      {item && <span className="rounded-full border px-2.5 py-1">
                        {item.reviewed_at ? (item.stale_evidence ? "Previously reviewed" : "Reviewed") : "Draft"} · Mapping r{item.revision}
                      </span>}
                    </div>
                    <h2 className="whitespace-pre-wrap break-words text-lg font-semibold">{requirement.statement}</h2>
                    <Link className="text-sm font-medium text-brand hover:underline"
                      href={`${context.href}/${requirement.session_id}/plan#item-${requirement.id}`}>
                      Open approved requirement
                    </Link>
                  </div>
                  {item ? (
                    <>
                      <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{item.rationale}</p>
                      {item.capability && (
                        <section className="space-y-2 rounded-lg border p-4" aria-label="Pinned catalog evidence">
                          <h3 className="break-words text-sm font-semibold">{item.capability.name}</h3>
                          <CatalogEvidence item={item.capability} />
                        </section>
                      )}
                      {context.canWrite && <MappingControls key={`${item.id}:${item.revision}:${item.reviewed_at}:${item.stale_evidence}`}
                        params={identifiers} release={board.release.id} item={item} entries={board.capabilities} />}
                    </>
                  ) : <p className="text-sm text-muted-foreground">Awaiting mapping.</p>}
                </article>
              );
            })}
          </section>
        </>
      ) : <p className="opportunity-panel p-5 text-sm">
        Add a product release in the{" "}
        <Link className="font-semibold text-brand hover:underline" href={`/workspaces/${identifiers.workspaceId}/catalog`}>capability catalog</Link>{" "}
        to map requirements.
      </p>}
    </div>
  );
}
