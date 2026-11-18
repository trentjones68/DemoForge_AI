import { Layers3 } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { signOut } from "@/app/sign-in/actions";
import { requireSession } from "@/lib/workspaces";

import { ThemeSwitch } from "./theme-switch";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({ children }: { children: ReactNode }) {
  await requireSession();
  return (
    <div className="mx-auto max-w-7xl px-4 py-4 sm:px-8 sm:py-6">
      <header className="flex items-center justify-between gap-4 border-b pb-4">
        <Link href="/workspaces" className="flex min-w-0 items-center gap-2 font-semibold tracking-tight hover:underline">
          <span className="shrink-0 rounded-lg bg-brand p-2 text-brand-foreground"><Layers3 size={16} aria-hidden="true" /></span>
          <span>DemoForge AI</span>
        </Link>
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <ThemeSwitch />
          <form action={signOut}>
            <button type="submit" className="button-secondary">Sign out</button>
          </form>
        </div>
      </header>
      <main className="py-6 sm:py-9">{children}</main>
    </div>
  );
}
