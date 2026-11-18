import { Moon, Sun } from "lucide-react";
import { cookies } from "next/headers";

import { getTheme } from "@/lib/theme";

async function setTheme(form: FormData) {
  "use server";
  const theme = form.get("theme");
  if (theme === "light" || theme === "dark") {
    (await cookies()).set("demoforge-theme", theme, {
      path: "/",
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 365,
    });
  }
}

export async function ThemeSwitch() {
  const theme = await getTheme();
  return (
    <form action={setTheme} aria-label="Color theme" className="flex rounded-lg border bg-background p-0.5">
      <button type="submit" name="theme" value="light" aria-label="Light theme" aria-pressed={theme === "light"} className="theme-option">
        <Sun size={16} aria-hidden="true" />
      </button>
      <button type="submit" name="theme" value="dark" aria-label="Dark theme" aria-pressed={theme === "dark"} className="theme-option">
        <Moon size={16} aria-hidden="true" />
      </button>
    </form>
  );
}
