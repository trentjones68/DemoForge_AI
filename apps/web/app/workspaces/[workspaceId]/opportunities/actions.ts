"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { detailSchema, opportunityInput, type FormState } from "@/lib/opportunity-fields";
import { loadOpportunityContext } from "@/lib/opportunities";
import { workspaceApi } from "@/lib/workspaces";

function textValue(form: FormData, name: string) {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

export async function saveOpportunity(
  workspaceId: string,
  opportunityId: string | null,
  version: number | null,
  _: FormState,
  form: FormData,
): Promise<FormState> {
  const context = await loadOpportunityContext(workspaceId);
  const values = {
    name: textValue(form, "name"),
    company: textValue(form, "company"),
    stage: textValue(form, "stage"),
    product: textValue(form, "product"),
    demo_date: textValue(form, "demo_date"),
    use_case: textValue(form, "use_case"),
    notes: textValue(form, "notes"),
    owner_id: textValue(form, "owner_id"),
  };
  const parsed = opportunityInput.safeParse(values);
  if (!parsed.success) {
    return { message: "Check the highlighted fields.", errors: z.flattenError(parsed.error).fieldErrors, values };
  }
  if (opportunityId !== null && (!z.uuid().safeParse(opportunityId).success || version === null)) {
    return { message: "Reload the opportunity and try again.", values: parsed.data };
  }

  const body = {
    ...parsed.data,
    demo_date: parsed.data.demo_date || null,
    owner_id: parsed.data.owner_id || null,
    ...(opportunityId ? { version } : {}),
  };
  const response = await workspaceApi(
    context.token,
    opportunityId ? `${context.apiPath}/${opportunityId}` : context.apiPath,
    { method: opportunityId ? "PUT" : "POST", body },
  );
  if (!response.ok) {
    const message = response.status === 409
      ? "This opportunity changed. Reload it before saving again."
      : response.status === 403 ? "You don’t have permission to save this opportunity."
      : response.status === 422 ? "Check the opportunity details and choose an eligible owner."
      : "Could not save the opportunity. Try again.";
    return { message, values: parsed.data };
  }

  const saved = detailSchema.parse(await response.json());
  revalidatePath(context.base);
  redirect(`${context.base}/${saved.id}`);
}

export async function archiveOpportunity(
  workspaceId: string, opportunityId: string, version: number,
): Promise<FormState> {
  const context = await loadOpportunityContext(workspaceId);
  if (!z.uuid().safeParse(opportunityId).success) {
    return { message: "Reload the opportunity and try again." };
  }
  const response = await workspaceApi(context.token, `${context.apiPath}/${opportunityId}/archive`, {
    method: "POST", body: { version },
  });
  if (!response.ok) {
    return {
      message: response.status === 409 ? "This opportunity changed. Reload it and try again."
        : response.status === 403 ? "You don’t have permission to archive this opportunity."
        : "Could not archive the opportunity. Try again.",
    };
  }
  revalidatePath(context.base);
  redirect(`${context.base}?archive=archived`);
}
