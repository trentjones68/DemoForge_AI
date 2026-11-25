import { z } from "zod";

import { releaseSchema, supportStatus } from "@/lib/catalog-fields";

export const revisionNumber = z.number().int().min(1).max(250);
export const uuid = z.uuid();
const label = z.string().trim().min(1).max(160);
const note = z.string().trim().min(1).max(2400);
const notes = z.array(note).max(6);
export const minutes = z.number().int().min(1).max(180);
export const briefSchema = z.object({
  audience: label, target_minutes: minutes, business_outcomes: z.array(label).min(1).max(5),
});
export const copySchema = z.object({
  title: label, actions: notes.min(1), talk_track: note, expected_outcome: note,
  synthetic_data: notes, risks: notes,
});
export const slotSchema = z.object({ id: uuid, minutes });
const copyField = copySchema.keyof();
const priority = z.enum(["high", "medium", "low"]);
const catalogRef = z.object({
  id: uuid, revision: z.number().int().positive(), name: z.string(),
  source_title: z.string(), source_url: z.url({ protocol: /^https$/ }),
  source_locator: z.string(), limitations: z.string(), dependencies: z.array(z.string()),
});
const evidenceSchema = z.object({
  session_id: uuid, requirement_id: uuid, requirement_revision: z.number().int().positive(),
  requirement: z.string(), priority, mapping_id: uuid, mapping_revision: z.number().int().positive(),
  support_status: supportStatus, mapping_rationale: z.string(), capability: catalogRef.nullable(),
});
const gapSchema = z.object({
  id: uuid, revision: z.number().int().positive(), question: z.string(), priority,
  status: z.enum(["open", "in_progress"]),
});
export const sceneSchema = slotSchema.extend({
  content: copySchema, evidence: evidenceSchema, gaps: z.array(gapSchema), edited_fields: z.array(copyField),
  stale_evidence: z.boolean(), support_warning: z.string().nullable(),
});
const timestamp = z.iso.datetime({ offset: true });
const revisionSchema = z.object({
  revision: revisionNumber, action: z.enum(["generated", "scene_edited", "agenda_updated", "scene_regenerated"]),
  actor_id: uuid, created_at: timestamp, approved_at: timestamp.nullable(), approved_by: uuid.nullable(),
});
export const storyboardSchema = revisionSchema.extend({
  schema_version: z.literal(1), id: uuid, release: releaseSchema,
  brief: briefSchema, scenes: z.array(sceneSchema).min(1).max(40),
});
export const studioSchema = z.object({
  current_revision: revisionNumber, revisions: z.array(revisionSchema), storyboard: storyboardSchema,
});
export const listSchema = z.array(z.object({
  id: uuid, revision: revisionNumber, release: releaseSchema, audience: label,
}));
export const fingerprintSchema = z.string().regex(/^[a-f0-9]{64}$/);
export const proposalSchema = z.object({ scene: sceneSchema, fingerprint: fingerprintSchema });

export type Scene = z.infer<typeof sceneSchema>;
export type SceneCopy = z.infer<typeof copySchema>;
export type Proposal = z.infer<typeof proposalSchema>;
export type Slot = z.infer<typeof slotSchema>;
export type Storyboard = z.infer<typeof storyboardSchema>;
