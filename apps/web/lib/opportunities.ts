import { notFound } from "next/navigation";
import { cache } from "react";
import { z } from "zod";

import { detailSchema, pageSchema, type Opportunity } from "@/lib/opportunity-fields";
import { requireIdentity, workspaceApi, workspaceSchema } from "@/lib/workspaces";

export const loadOpportunityContext = cache(async (workspaceId: string) => {
  if (!z.uuid().safeParse(workspaceId).success) notFound();
  const identity = await requireIdentity();
  const response = await workspaceApi(identity.token, `/${workspaceId}`);
  if (!response.ok) throw new Error("Could not load the workspace");
  const workspace = workspaceSchema.parse(await response.json());
  return {
    ...identity,
    workspace,
    base: `/workspaces/${workspaceId}/opportunities`,
    apiPath: `/${workspaceId}/opportunities`,
    canCreate: workspace.role === "admin" || workspace.role === "sales_engineer",
  };
});

type Context = Awaited<ReturnType<typeof loadOpportunityContext>>;

export async function listOpportunities(context: Context, query: URLSearchParams) {
  const response = await workspaceApi(context.token, `${context.apiPath}?${query}`);
  if (!response.ok) throw new Error("Could not load opportunities");
  return pageSchema.parse(await response.json());
}

export async function loadOpportunity(context: Context, id: string) {
  if (!z.uuid().safeParse(id).success) notFound();
  const response = await workspaceApi(context.token, `${context.apiPath}/${id}`);
  if (!response.ok) throw new Error("Could not load the opportunity");
  return detailSchema.parse(await response.json());
}

export function canEdit(context: Context, opportunity: Opportunity) {
  return !opportunity.archived_at && (
    context.workspace.role === "admin" ||
    (context.workspace.role === "sales_engineer" && opportunity.owner_id === context.userId)
  );
}

const eligibleMembers = z.array(z.object({
  user_id: z.uuid(),
  role: workspaceSchema.shape.role,
}));

export async function loadOwners(context: Context) {
  if (context.workspace.role !== "admin") return [];
  const response = await workspaceApi(context.token, `/${context.workspace.id}/members`);
  if (!response.ok) throw new Error("Could not load eligible owners");
  return eligibleMembers.parse(await response.json())
    .filter((member) => member.role === "admin" || member.role === "sales_engineer")
    .map((member) => member.user_id);
}
