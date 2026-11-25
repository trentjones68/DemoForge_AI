"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { catalogContext, catalogError } from "@/lib/catalog";
import { capabilityInput, releaseInput, releaseSchema } from "@/lib/catalog-fields";
import { workspaceApi } from "@/lib/workspaces";

export type Result = { error?: string; message?: string };
const editTarget = z.object({ id: z.uuid(), revision: z.number().int().positive().max(2147483645) });
type Target = z.input<typeof editTarget>;

const lines = (data: FormData, key: string) => String(data.get(key) ?? "")
  .split(/\r?\n/).map((line) => line.trim()).filter(Boolean);

export async function addRelease(workspace: string, _: Result, form: FormData): Promise<Result> {
  const fields = releaseInput.safeParse({
    product: form.get("product"), version: form.get("version"),
  });
  if (!fields.success) return { error: "Enter a product name and version." };
  const context = await catalogContext(workspace);
  if (!context.canManage) return { error: "Catalog admin access required." };
  const response = await workspaceApi(context.token, context.releasesApi, {
    method: "POST", body: fields.data,
  });
  if (!response.ok) return catalogError(response);
  const saved = releaseSchema.parse(await response.json());
  redirect(`${context.catalogHref}?release=${saved.id}`);
}

export async function saveCapability(
  workspace: string, release: string, target: Target | null, _: Result, form: FormData,
): Promise<Result> {
  const selected = target ? editTarget.safeParse(target) : null;
  if (!z.uuid().safeParse(release).success || selected?.success === false) {
    return { error: "The catalog selection is invalid." };
  }
  const fields = capabilityInput.safeParse({
    name: form.get("name"), description: form.get("description"),
    support_status: form.get("support_status"), limitations: form.get("limitations"),
    dependencies: lines(form, "dependencies"), match_phrases: lines(form, "match_phrases"),
    source_title: form.get("source_title"), source_url: form.get("source_url"),
    source_locator: form.get("source_locator"),
  });
  if (!fields.success) return { error: "Check the fields and use an HTTPS documentation URL." };
  const context = await catalogContext(workspace);
  if (!context.canManage) return { error: "Catalog admin access required." };
  const path = `${context.releasesApi}/${release}/capabilities`;
  const response = await workspaceApi(context.token, selected ? `${path}/${selected.data.id}` : path, {
    method: selected ? "PUT" : "POST",
    body: selected ? { ...fields.data, revision: selected.data.revision } : fields.data,
  });
  if (!response.ok) return catalogError(response);
  revalidatePath(context.catalogHref);
  return { message: selected ? "Catalog revision saved." : "Capability added." };
}

export async function archiveCapability(workspace: string, release: string, target: Target): Promise<Result> {
  const selected = editTarget.safeParse(target);
  if (!z.uuid().safeParse(release).success || !selected.success) return { error: "Invalid capability revision." };
  const context = await catalogContext(workspace);
  if (!context.canManage) return { error: "Catalog admin access required." };
  const path = `${context.releasesApi}/${release}/capabilities/${selected.data.id}/archive`;
  const response = await workspaceApi(context.token, path, {
    method: "POST", body: { revision: selected.data.revision },
  });
  if (!response.ok) return catalogError(response);
  revalidatePath(context.catalogHref);
  return { message: "Capability archived." };
}
