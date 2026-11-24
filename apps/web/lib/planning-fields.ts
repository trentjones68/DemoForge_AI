import { z } from "zod";

export const categories = z.enum(["buyer", "kpi", "workflow", "integration", "general"]);
export const priorities = z.enum(["high", "medium", "low"]);
export const kinds = z.enum(["requirement", "gap"]);
export const gapStatuses = z.enum(["open", "in_progress", "resolved"]);

export type PlanningKind = z.infer<typeof kinds>;

export const categoryLabels = {
  buyer: "Buyer", kpi: "KPI", workflow: "Workflow", integration: "Integration", general: "General",
};
export const gapStatusLabels = {
  open: "Open", in_progress: "In progress", resolved: "Resolved",
};
