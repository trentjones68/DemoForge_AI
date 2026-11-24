"use server";

import { redirect } from "next/navigation";
import { z } from "zod";

import { importResultSchema, loadDiscoveryContext, sessionSchema } from "@/lib/discovery";
import { workspaceApi } from "@/lib/workspaces";

const sessionInput = z.object({
  title: z.string().trim().min(1).max(120),
  occurred_on: z.union([z.literal(""), z.iso.date()]),
});
const kinds = z.enum(["transcript", "summary"]);
const providers = z.enum(["manual", "plaud"]);
const errorSchema = z.object({ detail: z.string().max(250) });
const uploadLimit = 2 * 1024 * 1024;

export type FormState = { error?: string };

async function errorMessage(response: Response, fallback: string): Promise<FormState> {
  const parsed = errorSchema.safeParse(await response.json().catch(() => null));
  return { error: parsed.success ? parsed.data.detail : fallback };
}

export async function createSession(
  workspaceId: string, opportunityId: string, _: FormState, data: FormData,
): Promise<FormState> {
  const parsed = sessionInput.safeParse({
    title: data.get("title"),
    occurred_on: data.get("occurred_on"),
  });
  if (!parsed.success) return { error: "Enter a session title and an optional date." };
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  if (!context.canWrite) return { error: "You do not have permission to create a discovery session." };
  const response = await workspaceApi(context.token, context.apiPath, {
    method: "POST",
    body: { title: parsed.data.title, occurred_on: parsed.data.occurred_on || null },
  });
  if (!response.ok) return errorMessage(response, "The session could not be created. Try again.");
  const session = sessionSchema.parse(await response.json());
  redirect(`${context.href}/${session.id}`);
}

export async function importSource(
  workspaceId: string, opportunityId: string, sessionId: string, _: FormState, data: FormData,
): Promise<FormState> {
  const kind = kinds.safeParse(data.get("kind"));
  const provider = providers.safeParse(data.get("provider"));
  if (!kind.success || !provider.success || !z.uuid().safeParse(sessionId).success) {
    return { error: "Choose a source type and provenance." };
  }
  if (data.get("consent") !== "on") {
    return { error: "Confirm recording and import consent before continuing." };
  }
  let raw: File | string;
  const headers: Record<string, string> = { "X-Import-Consent": "true" };
  if (data.get("method") === "file") {
    const file = data.get("file");
    if (!(file instanceof File) || !file.size) return { error: "Choose a transcript or summary file." };
    if (file.size > uploadLimit) return { error: "Choose a file no larger than 2 MiB." };
    raw = file;
    headers["Content-Type"] = file.type || "application/octet-stream";
    headers["X-Source-Filename"] = encodeURIComponent(file.name);
  } else {
    const pasted = data.get("transcript");
    if (typeof pasted !== "string" || !pasted.trim()) return { error: "Paste some source text first." };
    // Restore the textarea's LF value after multipart form encoding normalizes it to CRLF.
    raw = pasted.replace(/\r\n?/g, "\n");
    if (Buffer.byteLength(raw) > uploadLimit) return { error: "Split the text into smaller sources." };
    headers["Content-Type"] = "text/plain; charset=utf-8";
  }
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  if (!context.canWrite) return { error: "You do not have permission to import discovery sources." };
  const query = new URLSearchParams({ kind: kind.data, provider: provider.data });
  const response = await workspaceApi(context.token, `${context.apiPath}/${sessionId}/sources?${query}`, {
    method: "POST", raw, headers,
  });
  if (!response.ok) return errorMessage(response, "The import failed. Try again with the same source.");
  const { source, duplicate } = importResultSchema.parse(await response.json());
  redirect(`${context.href}/${sessionId}?source=${source.id}${duplicate ? "&duplicate=1" : ""}`);
}
