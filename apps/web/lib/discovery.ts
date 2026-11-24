import { notFound } from "next/navigation";
import { cache } from "react";
import { z } from "zod";

import { canEdit, loadOpportunity, loadOpportunityContext } from "@/lib/opportunities";
import { workspaceApi } from "@/lib/workspaces";

export const sessionSchema = z.object({
  id: z.uuid(),
  title: z.string(),
  occurred_on: z.iso.date().nullable(),
  created_at: z.iso.datetime({ offset: true }),
});

export const sourceSchema = z.object({
  id: z.uuid(),
  kind: z.enum(["transcript", "summary"]),
  provider: z.enum(["manual", "plaud"]),
  method: z.enum(["paste", "file"]),
  format: z.enum(["txt", "md", "docx", "pdf"]),
  filename: z.string().nullable(),
  byte_count: z.number().int().positive(),
  consent_at: z.iso.datetime({ offset: true }),
});

export const importResultSchema = z.object({ source: sourceSchema, duplicate: z.boolean() });

const evidenceSchema = z.object({
  source: sourceSchema,
  has_next: z.boolean(),
  segments: z.array(z.object({
    id: z.uuid(),
    ordinal: z.number().int().nonnegative(),
    start_offset: z.number().int().nonnegative(),
    end_offset: z.number().int().positive(),
    text: z.string(),
    speaker: z.string().nullable(),
    start_ms: z.number().int().nonnegative().nullable(),
    end_ms: z.number().int().nonnegative().nullable(),
  })),
});

export const loadDiscoveryContext = cache(async (workspaceId: string, opportunityId: string) => {
  const context = await loadOpportunityContext(workspaceId);
  if (context.workspace.role !== "admin" && context.workspace.role !== "sales_engineer") notFound();
  const opportunity = await loadOpportunity(context, opportunityId);
  return {
    ...context,
    opportunity,
    canWrite: canEdit(context, opportunity),
    href: `${context.base}/${opportunityId}/discovery`,
    apiPath: `${context.apiPath}/${opportunityId}/discovery`,
  };
});

type Context = Awaited<ReturnType<typeof loadDiscoveryContext>>;

export async function loadSessions(context: Context) {
  const response = await workspaceApi(context.token, context.apiPath);
  if (!response.ok) throw new Error("Could not load discovery sessions");
  return z.array(sessionSchema).parse(await response.json());
}

export async function loadSources(context: Context, sessionId: string) {
  const response = await workspaceApi(context.token, `${context.apiPath}/${sessionId}/sources`);
  if (!response.ok) throw new Error("Could not load discovery sources");
  return z.array(sourceSchema).parse(await response.json());
}

export async function loadEvidence(context: Context, sessionId: string, source: string, page: number) {
  const path = `${context.apiPath}/${sessionId}/sources/${source}/segments?page=${page}`;
  const response = await workspaceApi(context.token, path);
  if (!response.ok) throw new Error("Could not load source segments");
  return evidenceSchema.parse(await response.json());
}

export function sourceLabel(source: z.infer<typeof sourceSchema>) {
  if (source.filename) return source.filename;
  return source.kind === "summary" ? "Pasted summary" : "Pasted transcript";
}
