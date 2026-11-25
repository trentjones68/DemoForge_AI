"use client";

import { startTransition, useActionState, useState } from "react";

import { ReleaseSelect } from "@/app/workspaces/[workspaceId]/catalog/evidence";
import type { MappingParams } from "@/lib/catalog";
import type { Release } from "@/lib/catalog-fields";
import type { Scene, SceneCopy, Storyboard } from "@/lib/storyboard-fields";

import {
  applyScene, approveStoryboard, createStoryboard, editScene, previewScene, type Result, saveAgenda, type Target,
} from "./actions";
import { CopyDetails, copyLabels, EvidenceDetails } from "./scene-content";

function Feedback({ state }: { state: Result }) {
  return <>
    {state.error && <p role="alert" className="text-sm text-danger">{state.error}</p>}
    {state.message && <p role="status" className="text-sm text-muted-foreground">{state.message}</p>}
  </>;
}

export function GenerateForm({ params, releases }: { params: MappingParams; releases: Release[] }) {
  const [state, submit, pending] = useActionState(createStoryboard.bind(null, params), {});
  return (
    <form aria-label="New storyboard" className="space-y-4" onSubmit={(event) => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      startTransition(() => submit(fields));
    }}>
      <fieldset disabled={pending} className="grid gap-3 sm:grid-cols-3">
        <ReleaseSelect entries={releases} selected={releases[0]?.id} />
        <label className="grid gap-1.5 text-sm font-medium">Audience
          <input name="audience" className="opportunity-field" required maxLength={160} />
        </label>
        <label className="grid gap-1.5 text-sm font-medium">Duration (minutes)
          <input name="target_minutes" type="number" min={1} max={180} defaultValue={30} className="opportunity-field" required />
        </label>
        <label className="grid gap-1.5 text-sm font-medium sm:col-span-3">Business outcomes
          <textarea name="business_outcomes" className="opportunity-field" rows={3} required />
          <span className="text-xs text-muted-foreground">Enter up to five outcomes, one per line.</span>
        </label>
      </fieldset>
      <Feedback state={state} />
      <button type="submit" className="button-primary" disabled={pending}>{pending ? "Generating…" : "Generate storyboard"}</button>
    </form>
  );
}

export function AgendaControls({ params, board }: { params: MappingParams; board: Storyboard }) {
  const [scenes, setScenes] = useState(board.scenes);
  const [announcement, announce] = useState("");
  const [state, submit, pending] = useActionState(async () => saveAgenda(params,
    { id: board.id, revision: board.revision }, scenes.map(({ id, minutes }) => ({ id, minutes }))), {});
  const total = scenes.reduce((sum, scene) => sum + scene.minutes, 0);

  function move(index: number, direction: number) {
    const destination = index + direction;
    const next = [...scenes];
    [next[index], next[destination]] = [next[destination], next[index]];
    setScenes(next);
    announce(`${next[destination].content.title} moved to position ${destination + 1}.`);
  }

  return (
    <details className="opportunity-panel space-y-3 p-5">
      <summary className="cursor-pointer font-semibold text-brand">Reorder and time scenes</summary>
      <form action={submit} className="space-y-3">
        <fieldset disabled={pending}>
          <legend className="mb-2 text-sm font-medium">Agenda · {total} / {board.brief.target_minutes} minutes</legend>
          <ol className="space-y-2">{scenes.map((scene, index) => (
            <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3" key={scene.id}>
              <p className="min-w-0 break-words text-sm font-medium">{index + 1}. {scene.content.title}</p>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1 text-xs">Minutes
                  <input aria-label={`Minutes for scene ${index + 1}`} type="number" min={1} max={180} required
                    value={scene.minutes || ""} className="opportunity-field w-20" onChange={(event) => {
                      const value = Number(event.target.value);
                      setScenes(scenes.map((item) => item.id === scene.id ? { ...item, minutes: value } : item));
                    }} />
                </label>
                <button type="button" className="button-secondary" aria-label={`Move scene ${index + 1} up`}
                  disabled={index === 0} onClick={() => move(index, -1)}>Up</button>
                <button type="button" className="button-secondary" aria-label={`Move scene ${index + 1} down`}
                  disabled={index === scenes.length - 1} onClick={() => move(index, 1)}>Down</button>
              </div>
            </li>
          ))}</ol>
        </fieldset>
        <p className="sr-only" role="status">{announcement}</p>
        {total !== board.brief.target_minutes && <p className="text-sm text-muted-foreground">Allocate exactly {board.brief.target_minutes} minutes to save.</p>}
        <Feedback state={state} />
        <button type="submit" className="button-secondary" disabled={pending || total !== board.brief.target_minutes}>
          {pending ? "Saving…" : "Save agenda"}
        </button>
      </form>
    </details>
  );
}

export function SceneControls({ params, target, scene, provenance }: {
  params: MappingParams; target: Target; scene: Scene;
  provenance: { discovery: string; mapping: string; release: string };
}) {
  const [editState, save, saving] = useActionState(editScene.bind(null, params, target, scene.id), {});
  const [previewState, preview, previewing] = useActionState(previewScene.bind(null, params, target, scene.id), {});
  const proposal = previewState.proposal;
  const [applyState, apply, applying] = useActionState(async (_: Result, form: FormData) =>
    proposal ? applyScene(params, target, scene.id, proposal.fingerprint, form.get("replace") === "yes") : {}, {});
  const busy = saving || previewing || applying;
  const edited = (name: keyof SceneCopy) => scene.edited_fields.includes(name) ? " · Edited" : "";
  const fields = ["actions", "talk_track", "expected_outcome", "synthetic_data", "risks"] as const;

  return (
    <section className="space-y-4 border-t pt-4" aria-label="Scene editing and regeneration">
      <details className="space-y-3">
        <summary className="cursor-pointer font-semibold text-brand">Edit scene</summary>
        <form aria-label="Edit scene" className="space-y-3" onSubmit={(event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          startTransition(() => save(values));
        }}>
          <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm font-medium sm:col-span-2">{copyLabels.title}{edited("title")}
              <input name="title" className="opportunity-field" required maxLength={160} defaultValue={scene.content.title} />
            </label>
            {fields.map((field) => {
              const value = scene.content[field];
              return <label key={field} className="grid gap-1.5 text-sm font-medium">{copyLabels[field]}{edited(field)}
                <textarea name={field} className="opportunity-field" rows={3} maxLength={Array.isArray(value) ? 14405 : 2400}
                  required={["actions", "talk_track", "expected_outcome"].includes(field)}
                  defaultValue={Array.isArray(value) ? value.join("\n") : value} />
                {Array.isArray(value) && <span className="text-xs text-muted-foreground">One item per line, up to six.</span>}
              </label>;
            })}
          </fieldset>
          <Feedback state={editState} />
          <button type="submit" className="button-secondary" disabled={busy}>{saving ? "Saving…" : "Save scene"}</button>
        </form>
      </details>
      <form action={preview}>
        <button type="submit" className="button-secondary" disabled={busy}>{previewing ? "Preparing…" : "Preview regeneration"}</button>
        <Feedback state={previewState} />
      </form>
      {proposal && <div className="space-y-3 rounded-lg border bg-background p-4" aria-label="Regeneration proposal" role="region">
        <h3 className="font-semibold">Regeneration proposal</h3>
        <p className="break-words text-sm font-medium">{proposal.scene.content.title}</p>
        {proposal.scene.support_warning && <p className="text-sm font-semibold text-danger">{proposal.scene.support_warning}</p>}
        <CopyDetails copy={proposal.scene.content} discussion={proposal.scene.support_warning !== null} />
        <EvidenceDetails scene={proposal.scene} {...provenance} />
        <form action={apply} className="space-y-3">
          {scene.edited_fields.length > 0 && <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 accent-brand" name="replace" value="yes" disabled={busy} />
            Replace my edited fields in this scene. Leave unchecked to keep them.
          </label>}
          <Feedback state={applyState} />
          <button type="submit" className="button-primary" disabled={busy}>{applying ? "Applying…" : "Apply proposal"}</button>
        </form>
      </div>}
    </section>
  );
}

export function ApprovalControl({ params, target, hasWarnings }: { params: MappingParams; target: Target; hasWarnings: boolean }) {
  const [state, approve, pending] = useActionState(approveStoryboard.bind(null, params, target), {});
  return <form action={approve} className="space-y-3">
    {hasWarnings && <label className="flex items-start gap-2 text-sm">
      <input type="checkbox" required name="acknowledge" value="yes" className="mt-1 accent-brand" disabled={pending} />
      I reviewed the product support warnings and discussion-only scenes.
    </label>}
    <Feedback state={state} />
    <button type="submit" className="button-primary" disabled={pending}>{pending ? "Approving…" : "Approve revision"}</button>
  </form>;
}
