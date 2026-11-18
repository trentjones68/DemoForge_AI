"use server";

import { redirect } from "next/navigation";

import { createSupabaseClient } from "@/lib/supabase/server";

export async function signIn(form: FormData) {
  const email = form.get("email");
  const password = form.get("password");
  if (
    typeof email !== "string" || !email.trim() || email.length > 254 ||
    typeof password !== "string" || !password || password.length > 1024
  ) {
    redirect("/sign-in?error=credentials");
  }

  const supabase = await createSupabaseClient();
  if (!supabase) {
    redirect("/sign-in?error=unavailable");
  }
  const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
  if (error) {
    redirect(`/sign-in?error=${error.status && error.status >= 500 ? "unavailable" : "credentials"}`);
  }
  redirect("/workspaces");
}

export async function signOut() {
  const supabase = await createSupabaseClient();
  if (supabase) {
    const { error } = await supabase.auth.signOut({ scope: "local" });
    if (error) {
      redirect("/workspaces?error=sign-out");
    }
  }
  redirect("/sign-in");
}
