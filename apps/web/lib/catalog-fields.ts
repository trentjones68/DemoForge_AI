import { z } from "zod";

export const supportStatus = z.enum(["supported", "partial", "unsupported", "unknown"]);

export const supportLabels = {
  supported: "Supported", partial: "Partial", unsupported: "Unsupported", unknown: "Unknown",
};

export const releaseInput = z.object({
  product: z.string().trim().min(1).max(120),
  version: z.string().trim().min(1).max(80),
});

export const capabilityInput = z.object({
  name: z.string().trim().min(1).max(120),
  description: z.string().trim().min(1).max(800),
  support_status: supportStatus,
  limitations: z.string().max(800),
  dependencies: z.array(z.string().min(1).max(200)).max(12),
  match_phrases: z.array(z.string().min(1).max(800)).max(12),
  source_title: z.string().trim().min(1).max(200),
  source_url: z.url({ protocol: /^https$/ }).max(1200),
  source_locator: z.string().trim().min(1).max(200),
});

export const releaseSchema = releaseInput.extend({ id: z.uuid() });
export const capabilitySchema = capabilityInput.extend({
  id: z.uuid(), release_id: z.uuid(), revision: z.number().int().positive(), archived: z.boolean(),
});
export type Release = z.infer<typeof releaseSchema>;
export type Capability = z.infer<typeof capabilitySchema>;
