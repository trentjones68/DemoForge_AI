import { notFound } from "next/navigation";
import { z } from "zod";

import { type AnalysisParams, loadAnalysisContext } from "@/lib/analysis";
import { categories, gapStatuses, kinds, priorities } from "@/lib/planning-fields";
import { workspaceApi } from "@/lib/workspaces";

const revisionSchema = z.object({
  revision: z.number().int().positive(),
  statement: z.string(),
  rationale: z.string(),
  category: categories,
  priority: priorities,
  owner_id: z.uuid().nullable(),
  status: gapStatuses.nullable(),
  actor_id: z.uuid(),
  created_at: z.iso.datetime({ offset: true }),
  approved_at: z.iso.datetime({ offset: true }).nullable(),
  approved_by: z.uuid().nullable(),
  affected_requirement_ids: z.array(z.uuid()),
});
const itemSchema = revisionSchema.extend({
  id: z.uuid(),
  kind: kinds,
  generated: z.boolean(),
  stale_source: z.boolean(),
  source_revision: z.number().int().positive().nullable(),
  evidence: z.array(z.object({
    source_id: z.uuid(), segment_id: z.uuid(), page: z.number().int().positive(), quote: z.string(),
  })),
});
const planSchema = z.object({
  items: z.array(itemSchema), owners: z.array(z.uuid()), has_approved_insights: z.boolean(),
});
export const normalizedSchema = z.object({ added: z.number().int().nonnegative() });
export type PlanItem = z.infer<typeof itemSchema>;

export async function loadPlanningContext(params: AnalysisParams) {
  const context = await loadAnalysisContext(params);
  return {
    ...context,
    planHref: `${context.sessionHref}/plan`,
    planApi: `${context.apiPath}/${params.sessionId}/plan`,
  };
}

type Context = Awaited<ReturnType<typeof loadPlanningContext>>;

export async function readPlan(context: Context) {
  const response = await workspaceApi(context.token, context.planApi);
  if (!response.ok) throw new Error("Could not load the discovery plan");
  return planSchema.parse(await response.json());
}

export async function readHistory(context: Context, id: string) {
  if (!z.uuid().safeParse(id).success) notFound();
  const response = await workspaceApi(context.token, `${context.planApi}/items/${id}/history`);
  if (!response.ok) throw new Error("Could not load the revision history");
  return z.array(revisionSchema).parse(await response.json());
}
