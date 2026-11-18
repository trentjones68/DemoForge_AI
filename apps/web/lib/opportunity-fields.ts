import { z } from "zod";

export const stageSchema = z.enum([
  "discovery", "qualification", "demo_planning", "demo_scheduled",
  "follow_up", "closed_won", "closed_lost",
]);

export const stageLabels = {
  discovery: "Discovery",
  qualification: "Qualification",
  demo_planning: "Demo planning",
  demo_scheduled: "Demo scheduled",
  follow_up: "Follow-up",
  closed_won: "Closed won",
  closed_lost: "Closed lost",
} satisfies Record<z.infer<typeof stageSchema>, string>;

export const sortLabels = {
  recent: "Last updated",
  demo_date: "Demo date",
  name: "Name",
};

export const archiveSchema = z.enum(["active", "archived", "all"]);
export const sortSchema = z.enum(["recent", "demo_date", "name"]);

const label = z.string().trim().min(1, "Enter a value.").max(120, "Use 120 characters or fewer.");
export const opportunityInput = z.object({
  name: label,
  company: label,
  stage: stageSchema,
  product: label,
  demo_date: z.union([z.literal(""), z.iso.date({ error: "Enter a valid date." })]),
  use_case: z.string().trim().max(300, "Use 300 characters or fewer."),
  notes: z.string().trim().max(5000, "Use 5,000 characters or fewer."),
  owner_id: z.union([z.literal(""), z.uuid({ error: "Choose a valid owner." })]),
});

export const summarySchema = z.object({
  id: z.uuid(),
  workspace_id: z.uuid(),
  owner_id: z.uuid().nullable(),
  name: z.string(),
  company: z.string(),
  stage: stageSchema,
  product: z.string(),
  demo_date: z.iso.date().nullable(),
  archived_at: z.iso.datetime({ offset: true }).nullable(),
  created_at: z.iso.datetime({ offset: true }),
  updated_at: z.iso.datetime({ offset: true }),
  version: z.number().int(),
});

export const detailSchema = summarySchema.extend({
  use_case: z.string(),
  notes: z.string(),
});

export const pageSchema = z.object({
  items: z.array(summarySchema),
  page: z.number().int(),
  has_next: z.boolean(),
});

export type Opportunity = z.infer<typeof detailSchema>;
export type OpportunitySummary = z.infer<typeof summarySchema>;
export type OpportunityInput = z.infer<typeof opportunityInput>;
export type FormState = {
  message: string;
  errors?: Partial<Record<keyof OpportunityInput, string[]>>;
  values?: Record<keyof OpportunityInput, string>;
};

export function formatDemoDate(value: string | null) {
  return value
    ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(value))
    : "Unscheduled";
}

export function ownerLabel(ownerId: string | null, userId: string) {
  return ownerId === userId ? "You" : ownerId ? `Member ${ownerId.slice(0, 8)}` : "Unassigned";
}
