import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";

import { signIn } from "./actions";

export default async function SignIn({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const message = error === "unavailable"
    ? "Sign-in is temporarily unavailable."
    : error === "credentials" ? "Check your email and password and try again." : null;

  return (
    <main className="mx-auto grid min-h-dvh max-w-lg content-center gap-4 px-6 py-12">
      <Link href="/" className="text-sm font-semibold hover:underline">DemoForge AI</Link>
      <Card>
        <CardContent className="space-y-6">
          <h1 className="text-3xl font-semibold tracking-tight">Sign in</h1>
          <form action={signIn} className="space-y-4">
            {message && <p role="alert">{message}</p>}
            <div className="grid gap-1.5">
              <label htmlFor="email" className="text-sm font-medium">Email</label>
              <input id="email" name="email" type="email" autoComplete="username" required maxLength={254} className="rounded-md border px-3 py-2" />
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="password" className="text-sm font-medium">Password</label>
              <input id="password" name="password" type="password" autoComplete="current-password" required maxLength={1024} className="rounded-md border px-3 py-2" />
            </div>
            <button type="submit" className="w-full rounded-md bg-foreground px-4 py-2.5 font-medium text-background">Sign in</button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
