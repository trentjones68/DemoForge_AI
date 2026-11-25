"use client";

export default function DemoStudioError({ reset }: { reset: () => void }) {
  return <div className="opportunity-panel space-y-3 p-5">
    <h1 className="text-xl font-semibold">Could not load Demo Studio</h1>
    <p role="alert" className="text-sm text-muted-foreground">The storyboard service is temporarily unavailable.</p>
    <button type="button" onClick={reset} className="button-secondary">Try again</button>
  </div>;
}
