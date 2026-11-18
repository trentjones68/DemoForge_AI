"use client";

export default function OpportunitiesError({ retry }: { retry: () => void }) {
  return (
    <div className="opportunity-panel space-y-4 p-6">
      <h1 className="text-xl font-semibold">Could not load opportunities</h1>
      <p role="alert" className="text-sm text-muted-foreground">The opportunity service is temporarily unavailable.</p>
      <button type="button" onClick={retry} className="button-secondary">Try again</button>
    </div>
  );
}
