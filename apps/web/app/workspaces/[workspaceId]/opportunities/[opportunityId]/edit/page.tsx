import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { canEdit, loadOpportunity, loadOpportunityContext, loadOwners } from "@/lib/opportunities";

import { OpportunityForm } from "../../opportunity-form";

export default async function EditOpportunity({
  params,
}: {
  params: Promise<{ workspaceId: string; opportunityId: string }>;
}) {
  const { workspaceId, opportunityId } = await params;
  const context = await loadOpportunityContext(workspaceId);
  const item = await loadOpportunity(context, opportunityId);
  return (
    <div className="space-y-5">
      <Link href={`${context.base}/${item.id}`} className="inline-flex items-center gap-2 text-sm font-semibold text-brand hover:underline">
        <ArrowLeft size={16} aria-hidden="true" /> Opportunity details
      </Link>
      <h1 className="text-3xl font-semibold tracking-tight">Edit opportunity</h1>
      {canEdit(context, item) ? (
        <OpportunityForm workspaceId={workspaceId} base={context.base} userId={context.userId} owners={await loadOwners(context)} opportunity={item} />
      ) : <p className="opportunity-panel p-6" role="alert">{item.archived_at ? "Archived opportunities are read only." : "Only the assigned owner or a workspace admin can edit this opportunity."}</p>}
    </div>
  );
}
