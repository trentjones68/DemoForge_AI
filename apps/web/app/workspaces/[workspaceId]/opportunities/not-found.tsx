import Link from "next/link";

export default function OpportunityNotFound() {
  return (
    <div className="opportunity-panel space-y-4 p-6">
      <h1 className="text-xl font-semibold">Opportunity not found</h1>
      <p className="text-sm text-muted-foreground">This opportunity is unavailable in the selected workspace.</p>
      <Link href="/workspaces" className="button-secondary">Back to workspaces</Link>
    </div>
  );
}
