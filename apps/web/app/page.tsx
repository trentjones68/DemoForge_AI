import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";

export default function Home() {
  return (
    <main className="mx-auto grid min-h-dvh max-w-5xl content-center px-6 py-16 sm:px-12">
      <Card className="max-w-xl py-8 sm:py-12">
        <CardContent className="space-y-4 sm:px-12">
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            DemoForge AI
          </h1>
          <p className="text-muted-foreground max-w-md text-lg leading-relaxed">
            Turn discovery evidence into reviewed requirements and demo storyboards.
          </p>
          <Link href="/sign-in" className="inline-block rounded-md bg-foreground px-4 py-2 font-medium text-background">
            Sign in
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
