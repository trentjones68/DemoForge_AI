import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";

import {
  analysisFailures, type AnalysisParams, loadAnalysisContext, loadAnalysisOverview, loadReview,
} from "@/lib/analysis";

import { FindingEditor, RefreshWhileActive, StartAnalysis } from "./controls";

const statusLabels = {
  queued: "Queued", running: "Running", succeeded: "Complete", failed: "Failed",
};
const classLabels = {
  direct: "Direct evidence", inference: "Inference", unknown: "Unknown",
  contradictory: "Contradictory evidence",
};

export default async function AnalysisPage({
  params, searchParams,
}: {
  params: Promise<AnalysisParams>;
  searchParams: Promise<{ run?: string }>;
}) {
  const identifiers = await params;
  const context = await loadAnalysisContext(identifiers);
  const overview = await loadAnalysisOverview(context);
  const selection = (await searchParams).run ?? overview.runs[0]?.id;
  const review = selection ? await loadReview(context, selection) : null;
  const running = review?.run.status === "running" || review?.run.status === "queued";
  const activeRun = overview.runs.some((run) => run.status === "queued" || run.status === "running");

  return (
    <div className="space-y-6">
      <RefreshWhileActive running={activeRun} />
      <Link href={context.sessionHref} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> Discovery session
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Discovery analysis</h1>
          <p className="text-sm text-muted-foreground">Check each finding against its evidence before approving it.</p>
        </div>
        {context.canWrite && overview.enabled && <StartAnalysis params={identifiers} disabled={activeRun} />}
      </header>
      {!overview.enabled && (
        <p className="opportunity-panel p-5 text-sm">Analysis is disabled in this environment. Existing findings remain available for review.</p>
      )}
      {!review && <p className="opportunity-panel p-5 text-sm">No analysis runs yet. Import a transcript to begin.</p>}
      {overview.runs.length > 1 && (
        <nav className="opportunity-panel flex flex-wrap gap-2 p-4" aria-label="Analysis run history">
          {overview.runs.map((run) => (
            <Link key={run.id} href={`${context.analysisHref}?run=${run.id}`}
              aria-current={run.id === selection ? "page" : undefined}
              className="button-secondary aria-[current=page]:border-brand">
              <time dateTime={run.created_at}>{run.created_at.slice(0, 16).replace("T", " ")} UTC</time>
              <span>{statusLabels[run.status]}</span>
            </Link>
          ))}
        </nav>
      )}
      {review && (
        <section className="space-y-4" aria-label="Analysis results">
          <div className="opportunity-panel space-y-2 p-5">
            <p role="status" className="font-semibold">
              {statusLabels[review.run.status]}
              {running && ` · ${review.run.attempts} of 3 attempts started`}
            </p>
            <p className="break-words text-sm text-muted-foreground">
              {review.run.provider === "fake" ? "Synthetic development provider" : review.run.model} · {review.run.prompt_version}
            </p>
            {review.run.error_code && <p className="text-sm text-danger">{analysisFailures[review.run.error_code]}</p>}
            {review.run.status === "succeeded" && review.findings.length === 0 && (
              <p className="text-sm text-muted-foreground">The run returned zero findings.</p>
            )}
          </div>
          {review.findings.map((finding) => (
            <article key={finding.id} className="opportunity-panel min-w-0 space-y-4 p-5 sm:p-6">
              <div className="flex flex-wrap gap-2 text-xs font-medium">
                <span className="rounded-full bg-accent px-2.5 py-1 text-accent-foreground">
                  {classLabels[finding.classification]}
                </span>
                <span className="rounded-full border px-2.5 py-1 capitalize">{finding.kind.replaceAll("_", " ")}</span>
                <span className="rounded-full border px-2.5 py-1">
                  {finding.approved_at ? "Approved" : "Draft"} · Revision {finding.revision}
                </span>
              </div>
              <div className="space-y-2">
                <h2 className="whitespace-pre-wrap break-words text-lg font-semibold">{finding.statement}</h2>
                <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{finding.rationale}</p>
                <p className="text-xs text-muted-foreground">
                  Model confidence {Math.round(finding.confidence * 100)}%{finding.editor_id && " · Edited by a reviewer"}
                </p>
              </div>
              {finding.evidence.length > 0 && (
                <ul className="space-y-2" aria-label="Transcript evidence">
                  {finding.evidence.map((citation, index) => (
                    <li key={`${citation.segment_id}-${index}`} className="space-y-1 rounded-lg border p-3">
                      <blockquote className="whitespace-pre-wrap break-words text-sm">{citation.quote}</blockquote>
                      <Link className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline"
                        href={`${context.sessionHref}?source=${citation.source_id}&page=${citation.page}#segment-${citation.segment_id}`}>
                        Open transcript segment <ExternalLink size={14} aria-hidden="true" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {context.canWrite && (
                <FindingEditor key={`${finding.id}:${finding.revision}:${finding.approved_at}`}
                  params={identifiers} finding={finding} run={review.run.id} />
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
