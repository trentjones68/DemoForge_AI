import Link from "next/link";

import { supportLabels } from "@/lib/catalog-fields";
import type { Scene, SceneCopy } from "@/lib/storyboard-fields";

export const copyLabels: Record<keyof SceneCopy, string> = {
  title: "Scene title", actions: "Actions", talk_track: "Talk track", expected_outcome: "Expected outcome",
  synthetic_data: "Synthetic data needs", risks: "Demo risks",
};

export function CopyDetails({ copy, discussion }: { copy: SceneCopy; discussion: boolean }) {
  return (
    <dl className="grid min-w-0 gap-4 text-sm sm:grid-cols-2">
      <CopyList label={discussion ? "Discussion actions" : "Demo actions"} items={copy.actions} />
      <div className="space-y-1"><dt className="font-semibold">Talk track</dt><dd className="whitespace-pre-wrap break-words">{copy.talk_track}</dd></div>
      <div className="space-y-1"><dt className="font-semibold">Expected outcome</dt><dd className="whitespace-pre-wrap break-words">{copy.expected_outcome}</dd></div>
      <CopyList label="Synthetic data needs" items={copy.synthetic_data} />
      <CopyList label="Demo risks" items={copy.risks} />
    </dl>
  );
}

function CopyList({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return <div className="min-w-0 space-y-1"><dt className="font-semibold">{label}</dt><dd><ul className="list-inside list-disc space-y-1 break-words">
    {items.map((item, index) => <li key={index} className="whitespace-pre-wrap">{item}</li>)}
  </ul></dd></div>;
}

export function EvidenceDetails({ scene, discovery, mapping, release }: { scene: Scene; discovery: string; mapping: string; release: string }) {
  const source = scene.evidence;
  const ref = source.capability;
  const historyHref = (id: string, revision: number) =>
    `${discovery}/${source.session_id}/plan?history=${id}#plan-${id}-r${revision}`;
  return (
    <div className="space-y-3 border-t pt-4 text-sm">
      <p className="whitespace-pre-wrap break-words"><strong>Approved requirement r{source.requirement_revision}</strong> {source.requirement}</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <Link className="font-semibold text-brand hover:underline" href={historyHref(source.requirement_id, source.requirement_revision)}>Open requirement revision</Link>
        <Link className="font-semibold text-brand hover:underline" href={`${mapping}?release=${release}`}>Open mapping review</Link>
      </div>
      <p className="whitespace-pre-wrap break-words"><strong>{supportLabels[source.support_status]} · Mapping r{source.mapping_revision}</strong> {source.mapping_rationale}</p>
      {ref && <div className="space-y-1 rounded-lg border p-3 break-words">
        <p className="font-medium">{ref.name} · Catalog r{ref.revision}</p>
        <p><a className="font-semibold text-brand hover:underline" href={ref.source_url} target="_blank" rel="noopener noreferrer">{ref.source_title}</a> · {ref.source_locator}</p>
        {ref.limitations && <p className="whitespace-pre-wrap"><strong>Limitations</strong> {ref.limitations}</p>}
        {ref.dependencies.length > 0 && <p><strong>Integration dependencies</strong> {ref.dependencies.join(", ")}</p>}
      </div>}
      {scene.gaps.length > 0 && <div className="space-y-1">
        <p className="font-semibold">Unresolved discovery gaps at planning</p>
        <ul className="list-inside list-disc space-y-1 break-words">{scene.gaps.map((gap) => <li key={gap.id}>
          <Link className="text-brand hover:underline" href={historyHref(gap.id, gap.revision)}>{gap.question}</Link> · {gap.priority} priority · {gap.status === "open" ? "Open" : "In progress"}
        </li>)}</ul>
      </div>}
    </div>
  );
}
