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

export const requireSession = cache(async function requireSession() {
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
  return session.access_token;
});

export async function workspaceRequest(token: string, path = "", input?: { name: string }) {
  const baseUrl = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
  const response = await fetch(new URL(`/v1/workspaces${path}`, baseUrl), {
    method: input ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(input ? { "Content-Type": "application/json" } : {}),
    },
    body: input ? JSON.stringify(input) : undefined,
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
