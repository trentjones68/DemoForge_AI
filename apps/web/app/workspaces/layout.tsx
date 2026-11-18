import Link from "next/link";
import type { ReactNode } from "react";

import { signOut } from "@/app/sign-in/actions";
import { requireSession } from "@/lib/workspaces";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({ children }: { children: ReactNode }) {
  await requireSession();
  return (
    <div className="mx-auto max-w-4xl px-6 py-8 sm:px-10">
      <header className="flex items-center justify-between gap-4 border-b pb-4">
        <Link href="/workspaces" className="font-semibold hover:underline">DemoForge AI</Link>
        <form action={signOut}>
          <button type="submit" className="rounded-md border px-3 py-2 text-sm font-medium">Sign out</button>
        </form>
      </header>
      <main className="py-8">{children}</main>
    </div>
  );
}
