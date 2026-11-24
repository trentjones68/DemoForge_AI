import { ArrowLeft, Download, Link2 } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { loadDiscoveryContext, loadEvidence, loadSessions, loadSources, sourceLabel } from "@/lib/discovery";

import { ImportForm } from "../forms";

type Params = { workspaceId: string; opportunityId: string; sessionId: string };
const sourcePage = z.coerce.number().int().min(1).max(60).catch(1);

function timestamp(ms: number) {
  const whole = Math.floor(ms / 1000);
  const clock = [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60]
    .map((part) => String(part).padStart(2, "0")).join(":");
  return ms % 1000 ? `${clock}.${String(ms % 1000).padStart(3, "0")}` : clock;
}

export default async function DiscoverySession({
  params, searchParams,
}: {
  params: Promise<Params>;
  searchParams: Promise<{ source?: string; page?: string; duplicate?: string }>;
}) {
  const { workspaceId, opportunityId, sessionId } = await params;
  if (!z.uuid().safeParse(sessionId).success) notFound();
  const query = await searchParams;
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  const [sessions, sources] = await Promise.all([loadSessions(context), loadSources(context, sessionId)]);
  const session = sessions.find((entry) => entry.id === sessionId);
  if (!session) notFound();
  const selected = query.source ? sources.find((entry) => entry.id === query.source) : sources[0];
  if (query.source && !selected) notFound();
  const page = sourcePage.parse(query.page);
  const evidence = selected && await loadEvidence(context, sessionId, selected.id, page);
  const href = `${context.href}/${sessionId}`;

  return (
    <div className="space-y-6">
      <Link href={context.href} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> Discovery sessions
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 space-y-2">
          <h1 className="break-words text-3xl font-semibold tracking-tight sm:text-4xl">{session.title}</h1>
          {session.occurred_on && <p className="text-sm text-muted-foreground">Meeting date <time dateTime={session.occurred_on}>{session.occurred_on}</time></p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href={`${href}/analysis`} className="button-secondary">Discovery analysis</Link>
          <Link href={`${href}/plan`} className="button-secondary">Requirements and gaps</Link>
        </div>
      </header>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="space-y-4">
          <nav aria-label="Source documents" className="opportunity-panel">
            <h2 className="px-5 py-4 font-semibold">Source documents</h2>
            {sources.length ? (
              <ul className="divide-y border-t">
                {sources.map((source) => (
                  <li key={source.id}>
                    <Link
                      href={`${href}?source=${source.id}`}
                      aria-current={source.id === selected?.id ? "page" : undefined}
                      className="block break-words px-5 py-3 text-sm hover:bg-accent aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground"
                    >
                      <span className="font-medium">{sourceLabel(source)}</span>
                      <span className="block text-xs text-muted-foreground">
                        {source.kind === "summary" ? "Summary" : "Transcript"} · {source.provider === "plaud" ? "Plaud export" : "Manual"}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="px-5 pb-5 text-sm text-muted-foreground">No sources imported yet.</p>}
          </nav>
          {context.canWrite && <ImportForm key={selected?.id} workspaceId={workspaceId} opportunityId={opportunityId} sessionId={sessionId} />}
        </div>
        {evidence && (
          <section className="opportunity-panel min-w-0 divide-y" aria-labelledby="viewer-title">
            <header className="space-y-4 p-5 sm:p-6">
              {query.duplicate === "1" && <p role="status" className="text-sm text-muted-foreground">This source was already imported. Its existing segments are shown.</p>}
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 id="viewer-title" className="break-words text-xl font-semibold">{sourceLabel(evidence.source)}</h2>
                  <p className="text-sm text-muted-foreground">{evidence.source.kind === "summary" ? "Summary source" : "Transcript source"}</p>
                </div>
                {/* A plain anchor requests a newly authorized URL only when opened. */}
                <a href={`${href}/originals/${evidence.source.id}`} className="button-secondary">
                  <Download size={16} aria-hidden="true" /> Download original
                </a>
              </div>
              <dl className="grid gap-3 text-sm sm:grid-cols-3">
                <div><dt className="text-xs text-muted-foreground">Provenance</dt><dd>{evidence.source.provider === "plaud" ? "Manual Plaud export" : "Manual import"}</dd></div>
                <div><dt className="text-xs text-muted-foreground">Method</dt><dd>{evidence.source.method === "paste" ? "Pasted text" : `${evidence.source.format.toUpperCase()} upload`}</dd></div>
                <div><dt className="text-xs text-muted-foreground">Imported (UTC)</dt><dd><time dateTime={evidence.source.consent_at}>{evidence.source.consent_at.slice(0, 10)}</time></dd></div>
              </dl>
            </header>
            {evidence.segments.length ? (
              <ol className="divide-y" start={evidence.segments[0].ordinal + 1}>
                {evidence.segments.map((segment) => (
                  <li key={segment.id} id={`segment-${segment.id}`} className="scroll-mt-4 space-y-2 p-5 target:bg-accent sm:px-6">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <a href={`${href}?source=${evidence.source.id}&page=${page}#segment-${segment.id}`} className="inline-flex items-center gap-1 font-semibold text-brand hover:underline">
                        <Link2 size={14} aria-hidden="true" /> Segment {segment.ordinal + 1}
                      </a>
                      {segment.speaker && <span>{segment.speaker}</span>}
                      {segment.start_ms !== null && <span>{timestamp(segment.start_ms)}{segment.end_ms !== null && ` – ${timestamp(segment.end_ms)}`}</span>}
                      <span>Offsets {segment.start_offset}–{segment.end_offset}</span>
                    </div>
                    <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{segment.text}</p>
                  </li>
                ))}
              </ol>
            ) : <p className="p-5 text-sm text-muted-foreground">No segments on this page.</p>}
            {(page > 1 || evidence.has_next) && (
              <nav className="flex flex-wrap items-center gap-3 p-5 text-sm" aria-label="Transcript pages">
                {page > 1 && <Link className="button-secondary" href={`${href}?source=${evidence.source.id}&page=${page - 1}`}>Previous page</Link>}
                <span>Page {page}</span>
                {evidence.has_next && <Link className="button-secondary" href={`${href}?source=${evidence.source.id}&page=${page + 1}`}>Next page</Link>}
              </nav>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
