import { ArrowLeft, ChevronRight } from "lucide-react";
import Link from "next/link";

import { loadDiscoveryContext, loadSessions } from "@/lib/discovery";

import { SessionForm } from "./forms";

export default async function DiscoveryPage({
  params,
}: { params: Promise<{ workspaceId: string; opportunityId: string }> }) {
  const { workspaceId, opportunityId } = await params;
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  const sessions = await loadSessions(context);

  return (
    <div className="space-y-6">
      <Link href={`${context.base}/${opportunityId}`} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> {context.opportunity.name}
      </Link>
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Discovery sessions</h1>
        <p className="text-sm text-muted-foreground">Review transcripts and summaries for this opportunity.</p>
      </header>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        {context.canWrite && <SessionForm workspaceId={workspaceId} opportunityId={opportunityId} />}
        <section className="opportunity-panel" aria-label="Discovery sessions">
          {sessions.length ? (
            <ul className="divide-y">
              {sessions.map((session) => (
                <li key={session.id}>
                  <Link href={`${context.href}/${session.id}`} className="flex items-center justify-between gap-3 p-5 hover:bg-accent">
                    <div className="min-w-0">
                      <span className="break-words font-medium">{session.title}</span>
                      <p className="text-sm text-muted-foreground">
                        {session.occurred_on
                          ? <time dateTime={session.occurred_on}>{session.occurred_on}</time>
                          : "Meeting date unspecified"}
                      </p>
                    </div>
                    <ChevronRight size={18} className="shrink-0 text-muted-foreground" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="space-y-1 p-6">
              <h2 className="font-semibold">No discovery sessions yet</h2>
              {context.canWrite && <p className="text-sm text-muted-foreground">Create a session to start importing sources.</p>}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
