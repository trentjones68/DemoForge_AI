import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { loadOpportunityContext, loadOwners } from "@/lib/opportunities";

import { OpportunityForm } from "../opportunity-form";

export default async function NewOpportunity({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const context = await loadOpportunityContext(workspaceId);
  return (
    <div className="space-y-5">
      <Link href={context.base} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> Opportunities
      </Link>
      <h1 className="text-3xl font-semibold tracking-tight">New opportunity</h1>
      {context.canCreate ? (
        <OpportunityForm workspaceId={workspaceId} base={context.base} userId={context.userId} owners={await loadOwners(context)} />
      ) : <p className="opportunity-panel p-6" role="alert">Your workspace role can view opportunities. Ask a workspace admin to create one.</p>}
    </div>
  );
}
