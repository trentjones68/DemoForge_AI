import Link from "next/link";
import { z } from "zod";

import { Card, CardContent } from "@/components/ui/card";
import { requireSession, roleLabels, workspaceRequest, workspaceSchema } from "@/lib/workspaces";

import { createWorkspace } from "./actions";

export default async function Workspaces({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const token = await requireSession();
  const response = await workspaceRequest(token);
  if (!response.ok) {
    throw new Error("Could not load workspaces");
  }
  const workspaces = z.array(workspaceSchema).parse(await response.json());
  const { error } = await searchParams;
  const message = error === "create" ? "Could not create the workspace. Try again."
    : error === "invalid-name" ? "Enter a workspace name between 1 and 100 characters."
    : error === "sign-out" ? "Could not sign out. Try again." : null;

  return (
    <div className="grid gap-6">
      <h1 className="text-3xl font-semibold tracking-tight">Workspaces</h1>
      {message && <p role="alert">{message}</p>}
      {workspaces.length > 0 ? (
        <nav aria-label="Switch workspace">
          <ul className="grid gap-3">
            {workspaces.map((workspace) => (
              <li key={workspace.id}>
                <Link href={`/workspaces/${workspace.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-card px-4 py-3 hover:underline">
                  <span className="max-w-full break-words font-medium">{workspace.name}</span>
                  <span className="text-muted-foreground text-sm">{roleLabels[workspace.role]}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : <p className="text-muted-foreground">You don’t have any workspaces yet.</p>}
      <Card>
        <CardContent>
          <form action={createWorkspace} className="grid gap-3 sm:max-w-md">
            <label htmlFor="name" className="text-sm font-medium">New workspace name</label>
            <input id="name" name="name" maxLength={100} required className="rounded-md border px-3 py-2" />
            <button type="submit" className="w-fit rounded-md bg-foreground px-4 py-2 font-medium text-background">Create workspace</button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
