"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { catalogError, mappingContext, type MappingParams } from "@/lib/catalog";
import { workspaceApi } from "@/lib/workspaces";

export type Result = { error?: string; message?: string };
const revision = z.number().int().positive().max(2147483645);
const targetSchema = z.object({ id: z.uuid(), revision });
const evidenceChoice = z.tuple([z.uuid(), z.coerce.number().int().positive().max(2147483645)]);
const rationale = z.string().trim().min(1).max(800);

export async function generateMappings(params: MappingParams, release: string): Promise<Result> {
  if (!z.uuid().safeParse(release).success) return { error: "Select a product release." };
  const context = await mappingContext(params);
  if (!context.canWrite) return { error: "Opportunity write access required." };
  const response = await workspaceApi(context.token, `${context.mappingApi}/${release}/generate`, {
    method: "POST", body: {},
  });
  if (!response.ok) return catalogError(response);
  const result = z.object({ added: z.number().int().nonnegative() }).parse(await response.json());
  revalidatePath(context.mappingHref);
  return { message: result.added ? `Added ${result.added} mapping drafts.` : "Current requirements already have mapping drafts." };
}

export async function updateMapping(
  params: MappingParams, release: string, target: z.input<typeof targetSchema>,
  _: Result, form: FormData,
): Promise<Result> {
  const parsed = targetSchema.safeParse(target);
  const reason = rationale.safeParse(form.get("rationale"));
  const raw = form.get("evidence");
  const choice = typeof raw === "string" && raw ? evidenceChoice.safeParse(raw.split(":")) : null;
  if (!z.uuid().safeParse(release).success || !parsed.success || !reason.success || choice?.success === false) {
    return { error: "Select catalog evidence and enter a rationale." };
  }
  const context = await mappingContext(params);
  if (!context.canWrite) return { error: "Opportunity write access required." };
  const response = await workspaceApi(context.token, `${context.mappingApi}/${release}/items/${parsed.data.id}`, {
    method: "PUT",
    body: {
      revision: parsed.data.revision, rationale: reason.data,
      capability_id: choice?.data[0] ?? null, capability_revision: choice?.data[1] ?? null,
    },
  });
  if (!response.ok) return catalogError(response);
  revalidatePath(context.mappingHref);
  return { message: "Mapping draft saved." };
}

export async function reviewMapping(
  params: MappingParams, release: string, target: z.input<typeof targetSchema>,
): Promise<Result> {
  const parsed = targetSchema.safeParse(target);
  if (!z.uuid().safeParse(release).success || !parsed.success) return { error: "Invalid mapping revision." };
  const context = await mappingContext(params);
  if (!context.canWrite) return { error: "Opportunity write access required." };
  const response = await workspaceApi(context.token, `${context.mappingApi}/${release}/items/${parsed.data.id}/review`, {
    method: "POST", body: { revision: parsed.data.revision },
  });
  if (!response.ok) return catalogError(response);
  revalidatePath(context.mappingHref);
  return { message: "Mapping revision reviewed." };
}
