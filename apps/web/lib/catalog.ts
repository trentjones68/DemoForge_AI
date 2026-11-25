import { notFound } from "next/navigation";
import { z } from "zod";

import { capabilitySchema, releaseSchema, supportStatus } from "@/lib/catalog-fields";
import { loadDiscoveryContext } from "@/lib/discovery";
import { loadOpportunityContext } from "@/lib/opportunities";
import { workspaceApi } from "@/lib/workspaces";

const pageSchema = z.object({ entries: z.array(capabilitySchema), more: z.boolean() });
const mappingSchema = z.object({
  id: z.uuid(), revision: z.number().int().positive(),
  session_id: z.uuid(), requirement_id: z.uuid(), requirement_revision: z.number().int().positive(),
  support_status: supportStatus, rationale: z.string(), stale_evidence: z.boolean(),
  reviewed_at: z.iso.datetime({ offset: true }).nullable(), capability: capabilitySchema.nullable(),
});
const boardSchema = z.object({
  release: releaseSchema,
  requirements: z.array(z.object({
    id: z.uuid(), session_id: z.uuid(), statement: z.string(), revision: z.number().int().positive(),
  })),
  mappings: z.array(mappingSchema),
  capabilities: z.array(capabilitySchema),
});

export type Mapping = z.infer<typeof mappingSchema>;
export type MappingParams = { workspaceId: string; opportunityId: string };

export async function catalogContext(workspaceId: string) {
  const context = await loadOpportunityContext(workspaceId);
  if (context.workspace.role === "viewer") notFound();
  return {
    ...context,
    canManage: context.workspace.role === "admin" || context.workspace.role === "product_admin",
    catalogHref: `/workspaces/${workspaceId}/catalog`,
    releasesApi: `/${workspaceId}/catalog/releases`,
  };
}

type Catalog = Awaited<ReturnType<typeof catalogContext>>;

export async function releases(context: Pick<Catalog, "token" | "releasesApi">) {
  const response = await workspaceApi(context.token, context.releasesApi);
  if (!response.ok) throw new Error("Could not load catalog releases");
  return z.array(releaseSchema).parse(await response.json());
}

export async function capabilities(context: Catalog, release: string, params: URLSearchParams) {
  const response = await workspaceApi(context.token, `${context.releasesApi}/${release}/capabilities?${params}`);
  if (!response.ok) throw new Error("Could not load catalog capabilities");
  return pageSchema.parse(await response.json());
}

export async function mappingContext({ workspaceId, opportunityId }: MappingParams) {
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  const opportunityHref = `${context.base}/${opportunityId}`;
  return {
    ...context,
    opportunityHref,
    mappingHref: `${opportunityHref}/capability-mappings`,
    mappingApi: `/${workspaceId}/opportunities/${opportunityId}/capability-mappings`,
    releasesApi: `/${workspaceId}/catalog/releases`,
  };
}

type MappingContext = Awaited<ReturnType<typeof mappingContext>>;
export async function loadMappingBoard(context: MappingContext, release: string) {
  const response = await workspaceApi(context.token, `${context.mappingApi}/${release}`);
  if (!response.ok) throw new Error("Could not load capability mappings");
  return boardSchema.parse(await response.json());
}

export async function catalogError(response: Response): Promise<{ error: string }> {
  const result = z.object({ detail: z.string().max(250) })
    .safeParse(await response.json().catch(() => null));
  return { error: result.success ? result.data.detail : "The catalog action failed. Try again." };
}
