import type { Metadata } from "next";
import type { ReactNode } from "react";

import { getTheme } from "@/lib/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "DemoForge AI",
  description: "Discovery and demo planning for sales engineers.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme={await getTheme()}>
      <body>{children}</body>
    </html>
  );
}
