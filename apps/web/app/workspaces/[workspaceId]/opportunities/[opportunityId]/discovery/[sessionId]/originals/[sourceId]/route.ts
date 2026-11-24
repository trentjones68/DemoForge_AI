import { notFound } from "next/navigation";
import { z } from "zod";

import { loadDiscoveryContext } from "@/lib/discovery";
import { workspaceApi } from "@/lib/workspaces";

type Params = { workspaceId: string; opportunityId: string; sessionId: string; sourceId: string };
const download = z.object({ url: z.url({ protocol: /^https?$/ }) });
const privateHeaders = { "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" };

export async function GET(_: Request, { params }: { params: Promise<Params> }) {
  const { workspaceId, opportunityId, sessionId, sourceId } = await params;
  if (![sessionId, sourceId].every((value) => z.uuid().safeParse(value).success)) notFound();
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  const path = `${context.apiPath}/${sessionId}/sources/${sourceId}/original`;
  const response = await workspaceApi(context.token, path, { method: "POST", body: {} });
  const signed = download.safeParse(response.ok ? await response.json().catch(() => null) : null);
  if (!signed.success) {
    return new Response("The original is temporarily unavailable. Go back and try again.", {
      headers: privateHeaders, status: response.ok ? 503 : response.status,
    });
  }
  return new Response(null, {
    status: 303, headers: { ...privateHeaders, Location: signed.data.url },
  });
}
