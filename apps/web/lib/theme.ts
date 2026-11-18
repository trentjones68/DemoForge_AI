import { cookies } from "next/headers";

export async function getTheme() {
  return (await cookies()).get("demoforge-theme")?.value === "dark" ? "dark" : "light";
}
