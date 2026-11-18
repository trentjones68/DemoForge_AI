"use server";

import { redirect } from "next/navigation";

import { requireSession, workspaceRequest, workspaceSchema } from "@/lib/workspaces";

export async function createWorkspace(form: FormData) {
  const token = await requireSession();
  const name = form.get("name");
  if (typeof name !== "string" || !name.trim() || name.trim().length > 100) {
    redirect("/workspaces?error=invalid-name");
  }
  const response = await workspaceRequest(token, "", { name: name.trim() });
  if (!response.ok) {
    redirect("/workspaces?error=create");
  }
  const workspace = workspaceSchema.parse(await response.json());
  redirect(`/workspaces/${workspace.id}`);
}
