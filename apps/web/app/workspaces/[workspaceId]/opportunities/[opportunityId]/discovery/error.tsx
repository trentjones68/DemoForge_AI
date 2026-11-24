"use client";

export default function DiscoveryError({ reset }: { reset: () => void }) {
  return (
    <section className="opportunity-panel space-y-3 p-6">
      <h1 className="font-semibold">Discovery is temporarily unavailable</h1>
      <button className="button-secondary" type="button" onClick={reset}>Try again</button>
    </section>
  );
}
