import { notFound } from "next/navigation";
import { z } from "zod";

import { exportFormat, revisionNumber, uuid } from "@/lib/storyboard-fields";
import { studioContext } from "@/lib/storyboards";
import { workspaceApi } from "@/lib/workspaces";

const querySchema = z.object({ storyboard: uuid, revision: z.coerce.number().pipe(revisionNumber), format: exportFormat });
const privateHeaders = {
  "Cache-Control": "private, no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
};

export async function GET(request: Request, { params }: { params: Promise<{ workspaceId: string; opportunityId: string }> }) {
  const query = new URL(request.url).searchParams;
  const parsed = querySchema.safeParse({ storyboard: query.get("storyboard"), revision: query.get("revision"), format: query.get("format") });
  if (!parsed.success) notFound();
  const { workspaceId, opportunityId } = await params;
  const context = await studioContext(workspaceId, opportunityId);
  const { storyboard, revision, format } = parsed.data;
  const response = await workspaceApi(context.token, `${context.studioApi}/${storyboard}/export?revision=${revision}&format=${format}`);
  if (!response.ok) {
    const error = z.object({ detail: z.string().max(250) }).safeParse(await response.json().catch(() => null));
    return new Response(error.success ? error.data.detail : "This export is temporarily unavailable.", {
      status: response.status, headers: privateHeaders,
    });
  }
  return new Response(response.body, { headers: {
    ...privateHeaders,
    "Content-Type": format === "pdf" ? "application/pdf" : "text/markdown; charset=utf-8",
    "Content-Disposition": `attachment; filename="demo-storyboard-${storyboard}-r${revision}.${format}"`,
  } });
}
