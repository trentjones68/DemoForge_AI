import { ExternalLink } from "lucide-react";

import { type Capability, supportLabels } from "@/lib/catalog-fields";

export function ReleaseSelect({ entries, selected }: {
  entries: { id: string; product: string; version: string }[];
  selected: string | undefined;
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      Product release
      <select name="release" className="opportunity-field" defaultValue={selected}>
        {entries.map((entry) => <option key={entry.id} value={entry.id}>{entry.product} · {entry.version}</option>)}
      </select>
    </label>
  );
}

export function CatalogEvidence({ item }: { item: Capability }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="whitespace-pre-wrap break-words">{item.description}</p>
      <div className="flex flex-wrap gap-2 text-xs font-medium">
        <span className="rounded-full bg-accent px-2.5 py-1 text-accent-foreground">{supportLabels[item.support_status]}</span>
        <span className="rounded-full border px-2.5 py-1">Catalog revision {item.revision}</span>
        {item.archived && <span className="rounded-full border px-2.5 py-1">Archived</span>}
      </div>
      {item.limitations && <p className="whitespace-pre-wrap break-words"><strong>Limitations</strong> {item.limitations}</p>}
      {item.dependencies.length > 0 && (
        <div>
          <p className="font-medium">Integration dependencies</p>
          <ul className="list-inside list-disc break-words text-muted-foreground">
            {item.dependencies.map((dependency, index) => <li key={index}>{dependency}</li>)}
          </ul>
        </div>
      )}
      <div className="break-words">
        <a href={item.source_url} className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
          target="_blank" rel="noopener noreferrer">
          {item.source_title}<ExternalLink size={14} aria-hidden="true" />
        </a>
        <p className="text-xs text-muted-foreground">{item.source_locator}</p>
      </div>
    </div>
  );
}
