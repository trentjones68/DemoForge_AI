import assert from "node:assert/strict";

import { chromium } from "playwright";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const executablePath = process.env.DEMOFORGE_BROWSER_EXECUTABLE;
const browser = await chromium.launch(executablePath ? { executablePath } : {});
const plan = new URL(config.plan, config.base).href;

async function signIn(account) {
  const page = await browser.newPage({ viewport: { width: 390, height: 840 } });
  page.setDefaultTimeout(12_000);
  await page.goto(`${config.base}/sign-in`);
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await Promise.all([
    page.waitForURL("**/workspaces"),
    page.getByRole("button", { name: "Sign in" }).click(),
  ]);
  return page;
}

try {
  const page = await signIn(config.owner);
  await page.goto(plan);
  const generate = page.getByRole("button", { name: "Generate drafts" });
  assert.equal(await generate.isDisabled(), true);
  await page.getByRole("link", { name: "Approve a discovery finding" }).click();
  const insight = page.getByRole("article").filter({ hasText: config.statement });
  await insight.getByRole("button", { name: "Approve this revision" }).click();
  await insight.getByText("Approved · Revision 1").waitFor();
  await page.getByRole("link", { name: "Requirements and gaps" }).click();
  await generate.focus();
  await page.keyboard.press("Enter");

  const card = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: config.statement, exact: true }),
  });
  await card.getByText("Draft · Revision 1").waitFor();
  await page.getByRole("heading", { name: "Who is the economic buyer and who can give final approval?" }).waitFor();
  await page.getByRole("heading", { name: "Which KPI, baseline, and target will define success?" }).waitFor();
  await card.getByRole("link", { name: "Open transcript segment" }).click();
  await page.waitForURL(/#segment-/);
  await page.getByRole("heading", { name: "Pasted transcript" }).waitFor();
  await page.getByRole("link", { name: "Requirements and gaps" }).click();
  await card.getByRole("button", { name: "Approve this revision" }).click();
  await card.getByText("Approved · Revision 1").waitFor();

  const gaps = page.getByRole("region", { name: "Follow-up questions" });
  await gaps.locator("summary").filter({ hasText: /^Add gap$/ }).click();
  const addition = gaps.getByRole("form", { name: "Add gap" });
  await addition.getByLabel("Question").fill("Who owns report sign-off?");
  await addition.getByLabel("Rationale").fill("Confirm the sign-off sequence.");
  await addition.getByLabel("Owner").selectOption({ label: "You" });
  await addition.getByLabel("Status").selectOption("in_progress");
  await addition.getByRole("checkbox", { name: config.statement, exact: true }).check();
  await addition.getByRole("button", { name: "Add gap", exact: true }).click();
  const manual = gaps.getByRole("article").filter({ hasText: "Who owns report sign-off?" });
  await manual.getByText("In progress", { exact: true }).filter({ visible: true }).waitFor();
  await manual.getByRole("link", { name: config.statement, exact: true }).waitFor();
  await manual.getByRole("button", { name: "Approve this revision" }).click();
  await manual.getByText("Approved · Revision 1").waitFor();
  await manual.getByText("Edit item", { exact: true }).click();
  await manual.getByLabel("Status").selectOption("resolved");
  await manual.getByRole("button", { name: "Save as new draft" }).click();
  await manual.getByText("Draft · Revision 2").waitFor();
  await manual.getByText("Resolved", { exact: true }).filter({ visible: true }).waitFor();
  await manual.getByRole("link", { name: "Revision history" }).click();
  const history = page.getByRole("region", { name: "Revision history" });
  await history.getByText("Revision 2 · Draft").waitFor();
  await history.getByText("Revision 1 · Approved").waitFor();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));

  const peer = await signIn(config.peer);
  await peer.goto(plan);
  await peer.getByRole("heading", { name: config.statement, exact: true }).waitFor();
  assert.equal(await peer.getByRole("button", { name: "Generate drafts" }).count(), 0);
  assert.equal(await peer.getByText("Edit item", { exact: true }).count(), 0);
  assert.equal(await peer.getByRole("button", { name: "Approve this revision" }).count(), 0);

  const outsider = await signIn(config.outsider);
  await outsider.goto(plan);
  await outsider.getByRole("heading", { name: "Opportunity not found" }).waitFor();
  assert.equal(await outsider.getByText(config.statement, { exact: true }).count(), 0);
  console.log("Planning browser checks passed for draft generation, evidence, approval, edits, history, and permissions.");
} finally {
  await browser.close();
}
