import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { capabilities, catalogContext, releases } from "@/lib/catalog";

import { ArchiveEntry, EntryForm, NewRelease } from "./entries";
import { CatalogEvidence, ReleaseSelect } from "./evidence";

export default async function CatalogPage({
  params, searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ release?: string; q?: string; archived?: string; page?: string }>;
}) {
  const { workspaceId } = await params;
  const query = await searchParams;
  const context = await catalogContext(workspaceId);
  const products = await releases(context);
  const selected = query.release ? products.find((entry) => entry.id === query.release) : products[0];
  if (query.release && !selected) notFound();
  const search = typeof query.q === "string" ? query.q.slice(0, 120).trim() : "";
  const page = z.coerce.number().int().min(1).max(7).catch(1).parse(query.page);
  const filters = new URLSearchParams({
    q: search, include_archived: String(query.archived === "yes"), page: String(page),
  });
  const entries = selected ? await capabilities(context, selected.id, filters) : null;
  const pageHref = (value: number) => `?${new URLSearchParams({
    release: selected?.id ?? "", q: search, archived: query.archived === "yes" ? "yes" : "",
    page: String(value),
  })}`;

  return (
    <div className="space-y-6">
      <Link href={`/workspaces/${workspaceId}`} className="text-sm font-semibold text-brand hover:underline">Workspace</Link>
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Product capability catalog</h1>
        <p className="text-sm text-muted-foreground">Document product support and its source for each release.</p>
      </header>
      {context.canManage && <NewRelease workspace={workspaceId} />}
      {selected && entries ? (
        <>
          <form method="get" className="opportunity-panel space-y-4 p-5" role="search">
            <div className="grid gap-3 sm:grid-cols-2">
              <ReleaseSelect entries={products} selected={selected.id} />
              <label className="grid gap-1.5 text-sm font-medium">Search capabilities
                <input className="opportunity-field" name="q" type="search" maxLength={120} defaultValue={search} />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <button className="button-secondary" type="submit">Search catalog</button>
              <label className="inline-flex items-center gap-2 text-sm">
                <input type="checkbox" name="archived" value="yes" className="size-4 accent-brand" defaultChecked={query.archived === "yes"} />
                Include archived
              </label>
            </div>
          </form>
          {context.canManage && <div className="opportunity-panel p-5"><EntryForm key={selected.id} workspace={workspaceId} release={selected.id} /></div>}
          <section className="space-y-4" aria-label="Capabilities">
            {entries.entries.map((item) => (
              <article key={item.id} className="opportunity-panel min-w-0 space-y-4 p-5">
                <h2 className="break-words font-semibold">{item.name}</h2>
                <CatalogEvidence item={item} />
                {item.match_phrases.length > 0 && (
                  <div className="space-y-1 text-sm">
                    <p className="font-medium">Exact requirement phrases</p>
                    <ul className="list-inside list-disc break-words text-muted-foreground">
                      {item.match_phrases.map((phrase) => <li key={phrase}>{phrase}</li>)}
                    </ul>
                  </div>
                )}
                {context.canManage && !item.archived && (
                  <div className="flex flex-col gap-3 border-t pt-3">
                    <EntryForm key={item.revision} workspace={workspaceId} release={selected.id} item={item} />
                    <ArchiveEntry workspace={workspaceId} release={selected.id} item={item} />
                  </div>
                )}
              </article>
            ))}
            {entries.entries.length === 0 && <p className="opportunity-panel p-5 text-sm text-muted-foreground">No capabilities match this search.</p>}
          </section>
          {(page > 1 || entries.more) && (
            <nav aria-label="Catalog pages" className="flex items-center gap-3 text-sm">
              {page > 1 && <Link className="button-secondary" href={pageHref(page - 1)}>Previous page</Link>}
              <span>Page {page}</span>
              {entries.more && <Link className="button-secondary" href={pageHref(page + 1)}>Next page</Link>}
            </nav>
          )}
        </>
      ) : <p className="opportunity-panel p-5 text-sm text-muted-foreground">No product releases have been added.</p>}
    </div>
  );
}
