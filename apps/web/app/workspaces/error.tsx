"use client";

export default function WorkspaceError({ reset }: { reset: () => void }) {
  return (
    <div className="space-y-4">
      <p role="alert">The workspace service is temporarily unavailable.</p>
      <button type="button" onClick={reset} className="rounded-md border px-3 py-2 font-medium">Try again</button>
    </div>
  );
}
