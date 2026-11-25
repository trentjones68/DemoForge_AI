import { cache } from "react";

import { type MappingParams, mappingContext } from "@/lib/catalog";
import { listSchema, readinessSchema, studioSchema } from "@/lib/storyboard-fields";
import { workspaceApi } from "@/lib/workspaces";

export const studioContext = cache(async (workspaceId: string, opportunityId: string) => {
  const params: MappingParams = { workspaceId, opportunityId };
  const context = await mappingContext(params);
  return {
    ...context,
    params,
    studioApi: `/${workspaceId}/opportunities/${opportunityId}/storyboards`,
    studioHref: `${context.opportunityHref}/demo-studio`,
  };
});

type Context = Awaited<ReturnType<typeof studioContext>>;

export async function storyboards(context: Context) {
  const response = await workspaceApi(context.token, context.studioApi);
  if (!response.ok) throw new Error("Could not list storyboards");
  return listSchema.parse(await response.json());
}

export async function storyboard(context: Context, id: string, revision: number | undefined) {
  const query = revision ? `?revision=${revision}` : "";
  const response = await workspaceApi(context.token, `${context.studioApi}/${id}${query}`);
  if (!response.ok) throw new Error("Could not load the storyboard");
  return studioSchema.parse(await response.json());
}

export async function storyboardReadiness(context: Context, id: string, revision: number) {
  const response = await workspaceApi(context.token, `${context.studioApi}/${id}/readiness?revision=${revision}`);
  if (!response.ok) throw new Error("Could not load storyboard readiness");
  return readinessSchema.parse(await response.json());
}
