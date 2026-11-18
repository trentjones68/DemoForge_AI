export default function OpportunitiesLoading() {
  return (
    <div role="status" className="space-y-5">
      <p className="text-sm font-medium text-muted-foreground">Loading opportunities…</p>
      <div aria-hidden="true" className="opportunity-panel space-y-4 p-6 motion-safe:animate-pulse">
        <div className="h-4 w-36 rounded bg-accent" />
        <div className="h-12 rounded bg-background" />
        <div className="h-12 rounded bg-background" />
        <div className="h-12 rounded bg-background" />
      </div>
    </div>
  );
}
