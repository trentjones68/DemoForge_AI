import { notFound } from "next/navigation";
import { z } from "zod";

import { loadDiscoveryContext } from "@/lib/discovery";
import { workspaceApi } from "@/lib/workspaces";

const failureCode = z.enum([
  "input_limit", "invalid_output", "provider_unavailable", "provider_rejected",
  "access_revoked", "worker_interrupted", "configuration_changed",
]);
export const runSchema = z.object({
  id: z.uuid(),
  status: z.enum(["queued", "running", "succeeded", "failed"]),
  attempts: z.number().int().min(0).max(3),
  error_code: failureCode.nullable(),
  provider: z.enum(["openai", "fake"]),
  model: z.string(),
  prompt_version: z.string(),
  created_at: z.iso.datetime({ offset: true }),
});

const findingSchema = z.object({
  id: z.uuid(),
  revision: z.number().int().positive(),
  kind: z.enum([
    "pain_point", "goal", "requirement", "persona", "integration", "objection", "metric",
    "constraint", "success_criterion", "unknown",
  ]),
  classification: z.enum(["direct", "inference", "unknown", "contradictory"]),
  statement: z.string(),
  rationale: z.string(),
  confidence: z.number().min(0).max(1),
  editor_id: z.uuid().nullable(),
  approved_at: z.iso.datetime({ offset: true }).nullable(),
  approved_by: z.uuid().nullable(),
  evidence: z.array(z.object({
    source_id: z.uuid(), segment_id: z.uuid(), page: z.number().int().positive(), quote: z.string(),
  })),
});

export type Finding = z.infer<typeof findingSchema>;
export const reviewSchema = z.object({ run: runSchema, findings: z.array(findingSchema) });
const overviewSchema = z.object({ enabled: z.boolean(), runs: z.array(runSchema) });

export type AnalysisParams = {
  workspaceId: string;
  opportunityId: string;
  sessionId: string;
};

export async function loadAnalysisContext({ workspaceId, opportunityId, sessionId }: AnalysisParams) {
  if (!z.uuid().safeParse(sessionId).success) notFound();
  const context = await loadDiscoveryContext(workspaceId, opportunityId);
  return {
    ...context,
    sessionHref: `${context.href}/${sessionId}`,
    analysisHref: `${context.href}/${sessionId}/analysis`,
    analysisApi: `${context.apiPath}/${sessionId}/analysis`,
  };
}

type AnalysisContext = Awaited<ReturnType<typeof loadAnalysisContext>>;

export async function loadAnalysisOverview(context: AnalysisContext) {
  const response = await workspaceApi(context.token, context.analysisApi);
  if (!response.ok) throw new Error("Could not load discovery analysis");
  return overviewSchema.parse(await response.json());
}

export async function loadReview(context: AnalysisContext, run: string) {
  if (!z.uuid().safeParse(run).success) notFound();
  const response = await workspaceApi(context.token, `${context.analysisApi}/${run}`);
  if (!response.ok) throw new Error("Could not load findings");
  return reviewSchema.parse(await response.json());
}

export const analysisFailures: Record<z.infer<typeof failureCode>, string> = {
  input_limit: "This transcript exceeds the analysis size limit. Start a new session with a smaller transcript.",
  invalid_output: "The model returned results that did not pass evidence validation.",
  provider_unavailable: "The model provider was unavailable. Automatic retries are limited to three attempts.",
  provider_rejected: "The model provider rejected the request. Check the worker configuration.",
  access_revoked: "The opportunity became read-only or the requester lost access.",
  worker_interrupted: "The worker was interrupted and used all available attempts.",
  configuration_changed: "The worker configuration changed after this run was queued.",
};
