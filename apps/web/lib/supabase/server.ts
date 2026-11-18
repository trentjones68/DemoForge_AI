import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { authCookieOptions, supabaseConfig } from "./config";

export async function createSupabaseClient() {
  const config = supabaseConfig();
  if (!config) {
    return null;
  }

  const store = await cookies();
  return createServerClient(config.url, config.publishableKey, {
    cookieOptions: authCookieOptions,
    cookies: {
      getAll: () => store.getAll(),
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            store.set(name, value, options);
          }
        } catch {
          // Server components cannot set cookies. The proxy handles refresh there.
        }
      },
    },
  });
}
