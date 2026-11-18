import { ArrowDownUp, ArrowRight, BriefcaseBusiness, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import Link from "next/link";

import {
  archiveSchema, formatDemoDate, ownerLabel, sortLabels, sortSchema, stageLabels, stageSchema,
} from "@/lib/opportunity-fields";
import { listOpportunities, loadOpportunityContext } from "@/lib/opportunities";

const PAGE_SIZE = 10;

export default async function Opportunities({
  params, searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ workspaceId }, search] = await Promise.all([params, searchParams]);
  const context = await loadOpportunityContext(workspaceId);
  const archive = archiveSchema.safeParse(search.archive).data ?? "active";
  const sort = sortSchema.safeParse(search.sort).data ?? "recent";
  const stage = stageSchema.safeParse(search.stage).data;
  const pageValue = typeof search.page === "string" ? Number(search.page) : 1;
  const page = Number.isSafeInteger(pageValue) && pageValue >= 1 && pageValue <= 10000 ? pageValue : 1;

  function queryFor(targetPage: number, targetArchive = archive) {
    const query = new URLSearchParams({ archive: targetArchive, sort, page: String(targetPage) });
    if (stage) query.set("stage", stage);
    return query;
  }

  const query = queryFor(page);
  query.set("page_size", String(PAGE_SIZE));
  const result = await listOpportunities(context, query);
  const { items } = result;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link href={`/workspaces/${workspaceId}`} className="mb-2 inline-block max-w-full break-words text-sm font-semibold text-brand hover:underline">{context.workspace.name}</Link>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Opportunities</h1>
        </div>
        {context.canCreate && (
          <Link href={`${context.base}/new`} className="button-primary"><Plus size={16} aria-hidden="true" /> New opportunity</Link>
        )}
      </header>

      <div className="opportunity-panel overflow-hidden">
        <div className="flex flex-col gap-4 border-b px-4 py-4 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:px-5">
          <nav aria-label="Archive filter" className="flex w-fit max-w-full flex-wrap rounded-lg border bg-background p-1">
            {archiveSchema.options.map((item) => (
              <Link key={item} href={`${context.base}?${queryFor(1, item)}`} aria-current={item === archive ? "page" : undefined}
                className="rounded-md px-3 py-1.5 text-sm font-medium capitalize text-muted-foreground hover:text-foreground aria-[current=page]:bg-card aria-[current=page]:text-foreground aria-[current=page]:shadow-sm">
                {item}
              </Link>
            ))}
          </nav>
          <form action={context.base} className="grid grid-cols-2 items-end gap-2 sm:flex">
            <input type="hidden" name="archive" value={archive} />
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              Stage
              <select name="stage" defaultValue={stage ?? ""} className="opportunity-field py-2">
                <option value="">All stages</option>
                {Object.entries(stageLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              Sort by
              <select name="sort" defaultValue={sort} className="opportunity-field py-2">
                {Object.entries(sortLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
            </label>
            <button type="submit" className="button-secondary col-span-2 justify-self-start">
              <ArrowDownUp size={14} aria-hidden="true" /> Apply
            </button>
          </form>
        </div>

        {items.length === 0 ? (
          <div className="grid justify-items-center gap-3 px-5 py-14 text-center">
            <span className="rounded-xl bg-accent p-3 text-accent-foreground"><BriefcaseBusiness size={23} aria-hidden="true" /></span>
            <h2 className="text-lg font-semibold">{archive === "archived" && !stage && page === 1 ? "No archived opportunities" : "No opportunities to show"}</h2>
            {(stage || page > 1) ? (
              <Link className="button-secondary" href={`${context.base}?archive=${archive}`}>Reset filters and page</Link>
            ) : context.canCreate && archive !== "archived" ? (
              <Link className="button-primary" href={`${context.base}/new`}><Plus size={15} aria-hidden="true" /> Create an opportunity</Link>
            ) : null}
          </div>
        ) : (
          <>
            <table className="hidden w-full table-fixed text-left text-sm lg:table">
              <caption className="sr-only">Workspace opportunities</caption>
              <thead className="border-b bg-background text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="w-[32%] px-5 py-3 font-semibold">Opportunity / company</th>
                  <th scope="col" className="w-[18%] px-3 py-3 font-semibold">Stage</th>
                  <th scope="col" className="w-[18%] px-3 py-3 font-semibold">Product interest</th>
                  <th scope="col" className="w-[16%] px-3 py-3 font-semibold">Demo date</th>
                  <th scope="col" className="w-[16%] px-3 py-3 font-semibold">Owner</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((item) => (
                  <tr key={item.id} className="hover:bg-background">
                    <td className="px-5 py-4">
                      <Link href={`${context.base}/${item.id}`} className="block break-words font-semibold text-brand hover:underline">{item.name}</Link>
                      <span className="break-words text-muted-foreground">{item.company}</span>
                    </td>
                    <td className="px-3 py-4"><StageBadge stage={item.stage} />{item.archived_at && <span className="mt-1 block text-xs text-muted-foreground">Archived</span>}</td>
                    <td className="break-words px-3 py-4">{item.product}</td>
                    <td className="px-3 py-4">{formatDemoDate(item.demo_date)}</td>
                    <td className="px-3 py-4">{ownerLabel(item.owner_id, context.userId)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y lg:hidden">
              {items.map((item) => (
                <li key={item.id}>
                  <Link href={`${context.base}/${item.id}`} className="block space-y-3 p-4 hover:bg-background sm:p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="break-words font-semibold text-brand">{item.name}</p>
                        <p className="break-words text-sm text-muted-foreground">{item.company}</p>
                      </div>
                      <ArrowRight size={17} className="mt-1 shrink-0 text-brand" aria-hidden="true" />
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <StageBadge stage={item.stage} />
                      {item.archived_at && <span className="text-muted-foreground">Archived</span>}
                    </div>
                    <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                      <div className="min-w-0"><dt className="text-muted-foreground">Product interest</dt><dd className="break-words font-medium">{item.product}</dd></div>
                      <div><dt className="text-muted-foreground">Demo date</dt><dd className="font-medium">{formatDemoDate(item.demo_date)}</dd></div>
                      <div><dt className="text-muted-foreground">Owner</dt><dd className="font-medium">{ownerLabel(item.owner_id, context.userId)}</dd></div>
                    </dl>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}

        {(page > 1 || result.has_next) && (
          <nav aria-label="Opportunity pages" className="flex flex-wrap items-center justify-between gap-3 border-t p-4 text-sm">
            <span className="text-muted-foreground">Page {result.page}</span>
            <div className="flex gap-2">
              {page > 1 && <Link href={`${context.base}?${queryFor(page - 1)}`} className="button-secondary"><ChevronLeft size={15} aria-hidden="true" /> Previous</Link>}
              {result.has_next && <Link href={`${context.base}?${queryFor(page + 1)}`} className="button-secondary">Next <ChevronRight size={15} aria-hidden="true" /></Link>}
            </div>
          </nav>
        )}
      </div>
    </div>
  );
}

function StageBadge({ stage }: { stage: keyof typeof stageLabels }) {
  return <span className="inline-flex rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground">{stageLabels[stage]}</span>;
}
