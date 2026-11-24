"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import type { AnalysisParams } from "@/lib/analysis";
import { loadPlanningContext, normalizedSchema } from "@/lib/planning";
import { categories, gapStatuses, kinds, priorities } from "@/lib/planning-fields";
import { workspaceApi } from "@/lib/workspaces";

export type ActionState = { error?: string; message?: string };

const selectionSchema = z.object({
  id: z.uuid(),
  revision: z.number().int().min(1).max(2147483645),
});
type Selection = z.input<typeof selectionSchema>;
const inputSchema = z.object({
  statement: z.string().trim().min(1).max(800),
  rationale: z.string().trim().min(1).max(800),
  priority: priorities,
  category: categories,
  owner_id: z.uuid().nullable(),
  status: gapStatuses.nullable(),
  affected_requirement_ids: z.array(z.uuid()).max(16),
});

async function errorState(response: Response): Promise<ActionState> {
  const result = z.object({ detail: z.string().max(250) })
    .safeParse(await response.json().catch(() => null));
  return { error: result.success ? result.data.detail : "The action failed. Please try again." };
}

export async function generateDrafts(params: AnalysisParams): Promise<ActionState> {
  const context = await loadPlanningContext(params);
  if (!context.canWrite) return { error: "You do not have permission to generate drafts." };
  const response = await workspaceApi(context.token, `${context.planApi}/normalize`, {
    method: "POST", body: {},
  });
  if (!response.ok) return errorState(response);
  const result = normalizedSchema.parse(await response.json());
  revalidatePath(context.planHref);
  return { message: result.added ? `Added ${result.added} drafts.` : "The approved findings are already reflected in the plan." };
}

export async function saveItem(
  params: AnalysisParams, kind: z.input<typeof kinds>, target: Selection | null,
  _: ActionState, form: FormData,
): Promise<ActionState> {
  const parsedKind = kinds.safeParse(kind);
  const selected = target ? selectionSchema.safeParse(target) : null;
  if (!parsedKind.success || selected?.success === false) return { error: "Invalid planning item." };

  const result = inputSchema.safeParse({
    statement: form.get("statement"),
    rationale: form.get("rationale"),
    category: form.get("category"),
    priority: form.get("priority"),
    owner_id: form.get("owner_id") || null,
    status: form.get("status"),
    affected_requirement_ids: form.getAll("affected_requirements"),
  });
  if (!result.success) return { error: "Check the statement, rationale, and linked requirements." };
  const context = await loadPlanningContext(params);
  if (!context.canWrite) return { error: "You do not have permission to edit the plan." };
  const collection = `${context.planApi}/items`;
  const response = await workspaceApi(context.token, selected ? `${collection}/${selected.data.id}` : collection, {
    method: selected ? "PUT" : "POST",
    body: selected
      ? { ...result.data, revision: selected.data.revision }
      : { ...result.data, kind: parsedKind.data },
  });
  if (!response.ok) return errorState(response);
  revalidatePath(context.planHref);
  return { message: selected ? "Draft saved." : "Draft added." };
}

export async function approveItem(params: AnalysisParams, target: Selection): Promise<ActionState> {
  const selection = selectionSchema.safeParse(target);
  if (!selection.success) return { error: "Invalid item revision." };
  const context = await loadPlanningContext(params);
  if (!context.canWrite) return { error: "You do not have permission to approve items." };
  const endpoint = `${context.planApi}/items/${selection.data.id}/approve`;
  const response = await workspaceApi(context.token, endpoint, {
    method: "POST", body: { revision: selection.data.revision },
  });
  if (!response.ok) return errorState(response);
  revalidatePath(context.planHref);
  return { message: "Revision approved." };
}
