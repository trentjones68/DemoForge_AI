"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { type AnalysisParams, loadAnalysisContext, runSchema } from "@/lib/analysis";
import { workspaceApi } from "@/lib/workspaces";

export type ActionState = { error?: string };

const reviewTarget = z.object({
  run: z.uuid(),
  finding: z.uuid(),
  revision: z.coerce.number().int().min(1).max(2147483645),
});

const fieldsSchema = z.object({
  statement: z.string().trim().min(1).max(800),
  rationale: z.string().trim().min(1).max(800),
});

async function actionError(response: Response): Promise<ActionState> {
  const result = z.object({ detail: z.string().max(250) })
    .safeParse(await response.json().catch(() => null));
  return { error: result.success ? result.data.detail : "The action failed. Try again." };
}

export async function startAnalysis(params: AnalysisParams): Promise<ActionState> {
  const context = await loadAnalysisContext(params);
  if (!context.canWrite) return { error: "You do not have permission to start analysis." };
  const response = await workspaceApi(context.token, context.analysisApi, { method: "POST", body: {} });
  if (!response.ok) return actionError(response);
  const run = runSchema.parse(await response.json());
  redirect(`${context.analysisHref}?run=${run.id}`);
}

export async function reviewFinding(
  params: AnalysisParams, operation: "edit" | "approve", identifiers: z.input<typeof reviewTarget>,
  _: ActionState, data: FormData,
): Promise<ActionState> {
  const selection = reviewTarget.safeParse(identifiers);
  if (!selection.success || (operation !== "edit" && operation !== "approve")) {
    return { error: "This review action could not be identified." };
  }
  const { run, finding, revision } = selection.data;
  const context = await loadAnalysisContext(params);
  if (!context.canWrite) return { error: "You do not have permission to review findings." };
  const base = `${context.analysisApi}/${run}/findings/${finding}`;
  if (operation === "edit") {
    const fields = fieldsSchema.safeParse({
      statement: data.get("statement"),
      rationale: data.get("rationale"),
    });
    if (!fields.success) return { error: "Enter a statement and rationale of up to 800 characters each." };
    const response = await workspaceApi(context.token, base, {
      method: "PUT", body: { revision, ...fields.data },
    });
    if (!response.ok) return actionError(response);
  } else {
    const response = await workspaceApi(context.token, `${base}/approve`, {
      method: "POST", body: { revision },
    });
    if (!response.ok) return actionError(response);
  }
  revalidatePath(context.analysisHref);
  return {};
}
