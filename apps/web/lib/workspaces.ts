import { notFound, redirect } from "next/navigation";
import { cache } from "react";
import { z } from "zod";

import { createSupabaseClient } from "@/lib/supabase/server";

export const workspaceSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  role: z.enum(["admin", "product_admin", "sales_engineer", "viewer"]),
});

export const roleLabels = {
  admin: "Workspace admin",
  product_admin: "Product admin",
  sales_engineer: "Sales engineer",
  viewer: "Viewer",
};

export const requireIdentity = cache(async function requireIdentity() {
  const supabase = await createSupabaseClient();
  if (!supabase) {
    redirect("/sign-in?error=unavailable");
  }
  const { data: { user } } = await supabase.auth.getUser();
  if (!user || user.is_anonymous) {
    redirect("/sign-in");
  }

  // FastAPI verifies this access token again against its trusted issuer.
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    redirect("/sign-in");
  }
  return { token: session.access_token, userId: user.id };
});

export async function requireSession() {
  return (await requireIdentity()).token;
}

export async function workspaceRequest(token: string, path = "", input?: { name: string }) {
  return workspaceApi(token, path, input ? { method: "POST", body: input } : undefined);
}

export async function workspaceApi(
  token: string,
  path: string,
  request?: { method: "POST" | "PUT"; body: object },
) {
  const baseUrl = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL(`/v1/workspaces${path}`, baseUrl), {
    method: request?.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(request ? { "Content-Type": "application/json" } : {}),
    },
    body: request ? JSON.stringify(request.body) : undefined,
    cache: "no-store",
    signal: AbortSignal.timeout(7000),
  });

  if (response.status === 401) {
    redirect("/sign-in");
  }
  if (response.status === 404) {
    notFound();
  }
  return response;
}
