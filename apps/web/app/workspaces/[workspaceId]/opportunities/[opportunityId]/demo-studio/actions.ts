"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { catalogError, type MappingParams } from "@/lib/catalog";
import {
  briefSchema, copySchema, fingerprintSchema, type Proposal, proposalSchema, prepTask,
  readinessSchema, revisionNumber, type Slot, slotSchema, storyboardSchema, uuid,
} from "@/lib/storyboard-fields";
import { studioContext } from "@/lib/storyboards";
import { workspaceApi } from "@/lib/workspaces";

export type Result = { error?: string; message?: string; proposal?: Proposal };
const targetSchema = z.object({ id: uuid, revision: revisionNumber });
export type Target = z.infer<typeof targetSchema>;

function lines(value: FormDataEntryValue | null) {
  return typeof value === "string" ? value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean) : [];
}

async function send(params: MappingParams, path: string, method: "POST" | "PUT", body: object) {
  const context = await studioContext(params.workspaceId, params.opportunityId);
  if (!context.canWrite) return { error: "Opportunity write access required." };
  const response = await workspaceApi(context.token, `${context.studioApi}${path}`, { method, body });
  if (!response.ok) return catalogError(response);
  return { response, href: context.studioHref };
}

async function save(params: MappingParams, path: string, method: "POST" | "PUT", body: object, message: string): Promise<Result> {
  const result = await send(params, path, method, body);
  if ("error" in result) return result;
  storyboardSchema.parse(await result.response.json());
  revalidatePath(result.href);
  return { message };
}

export async function createStoryboard(params: MappingParams, _: Result, form: FormData): Promise<Result> {
  const input = briefSchema.extend({ release_id: uuid }).safeParse({
    release_id: form.get("release"), audience: form.get("audience"),
    target_minutes: Number(form.get("target_minutes")), business_outcomes: lines(form.get("business_outcomes")),
  });
  if (!input.success) return { error: "Choose a release, audience, a duration of 1–180 minutes, and one to five outcomes." };
  const result = await send(params, "", "POST", input.data);
  if ("error" in result) return result;
  const storyboard = storyboardSchema.parse(await result.response.json());
  revalidatePath(result.href);
  redirect(`${result.href}?storyboard=${storyboard.id}`);
}

export async function editScene(params: MappingParams, target: Target, scene: string, _: Result, form: FormData): Promise<Result> {
  const input = copySchema.safeParse({
    title: form.get("title"), actions: lines(form.get("actions")), talk_track: form.get("talk_track"),
    expected_outcome: form.get("expected_outcome"), synthetic_data: lines(form.get("synthetic_data")), risks: lines(form.get("risks")),
  });
  if (!targetSchema.safeParse(target).success || !uuid.safeParse(scene).success || !input.success) {
    return { error: "Enter a title, actions, a talk track, and an expected outcome. Use up to six lines per list." };
  }
  return save(params, `/${target.id}/scenes/${scene}`, "PUT", { ...input.data, revision: target.revision }, "Scene saved.");
}

export async function saveAgenda(params: MappingParams, target: Target, slots: Slot[]): Promise<Result> {
  if (!targetSchema.safeParse(target).success || !z.array(slotSchema).min(1).max(40).safeParse(slots).success) {
    return { error: "Enter whole minutes for every scene." };
  }
  return save(params, `/${target.id}/agenda`, "PUT", { revision: target.revision, scenes: slots }, "Agenda saved.");
}

export async function previewScene(params: MappingParams, target: Target, scene: string): Promise<Result> {
  if (!targetSchema.safeParse(target).success || !uuid.safeParse(scene).success) return { error: "Invalid scene revision." };
  const result = await send(params, `/${target.id}/scenes/${scene}/proposal`, "POST", { revision: target.revision });
  if ("error" in result) return result;
  return { proposal: proposalSchema.parse(await result.response.json()) };
}

export async function applyScene(params: MappingParams, target: Target, scene: string, fingerprint: string, replace: boolean): Promise<Result> {
  if (!targetSchema.safeParse(target).success || !uuid.safeParse(scene).success || !fingerprintSchema.safeParse(fingerprint).success) {
    return { error: "Preview this scene again before applying changes." };
  }
  return save(params, `/${target.id}/scenes/${scene}/apply`, "POST", {
    revision: target.revision, fingerprint, replace_edits: replace,
  }, "Scene proposal applied.");
}

export async function approveStoryboard(params: MappingParams, target: Target, _: Result, form: FormData): Promise<Result> {
  if (!targetSchema.safeParse(target).success) return { error: "Invalid storyboard revision." };
  return save(params, `/${target.id}/approve`, "POST", {
    revision: target.revision, acknowledge_warnings: form.get("acknowledge") === "yes",
  }, "Storyboard revision approved.");
}

export async function updatePreparation(params: MappingParams, target: Target, task: string, complete: boolean): Promise<Result> {
  if (!targetSchema.safeParse(target).success || !prepTask.safeParse(task).success || typeof complete !== "boolean") {
    return { error: "Invalid preparation item." };
  }
  const result = await send(params, `/${target.id}/readiness/${task}`, "PUT", { revision: target.revision, complete });
  if ("error" in result) return result;
  readinessSchema.parse(await result.response.json());
  revalidatePath(result.href);
  return { message: "Preparation updated." };
}
