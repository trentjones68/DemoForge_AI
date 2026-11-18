import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";

import { requireSession, roleLabels, workspaceRequest, workspaceSchema } from "@/lib/workspaces";

export default async function Workspace({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const token = await requireSession();
  const { workspaceId } = await params;
  if (!z.uuid().safeParse(workspaceId).success) {
    notFound();
  }
  const response = await workspaceRequest(token, `/${workspaceId}`);
  if (!response.ok) {
    throw new Error("Could not load workspace");
  }
  const workspace = workspaceSchema.parse(await response.json());
  return (
    <div className="space-y-4">
      <Link href="/workspaces" className="text-sm font-medium underline">Switch workspace</Link>
      <h1 className="text-3xl font-semibold tracking-tight break-words">{workspace.name}</h1>
      <p className="text-muted-foreground">{roleLabels[workspace.role]}</p>
      <Link href={`/workspaces/${workspace.id}/opportunities`} className="button-primary">
        Open opportunities
      </Link>
    </div>
  );
}
