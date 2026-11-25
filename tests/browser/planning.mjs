import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { chromium } from "playwright";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const executablePath = process.env.DEMOFORGE_BROWSER_EXECUTABLE;
const browser = await chromium.launch(executablePath ? { executablePath } : {});
const plan = new URL(config.plan, config.base).href;
const catalog = new URL(`${config.plan.split("/opportunities/")[0]}/catalog`, config.base).href;
const mappings = new URL(`${config.plan.split("/discovery/")[0]}/capability-mappings`, config.base).href;
const studio = new URL(`${config.plan.split("/discovery/")[0]}/demo-studio`, config.base).href;
const unknownRequirement = "Publish an automated compliance summary.";
const audience = "Synthetic compliance team";
const manualTrack = "Ask the team to verify the fictional audit totals.";
let exportHref;

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

async function createStoryboard(page) {
  await page.goto(studio);
  const newBoard = page.getByRole("form", { name: "New storyboard" });
  await newBoard.getByLabel("Audience").fill(audience);
  await newBoard.getByLabel("Duration (minutes)").fill("11");
  await newBoard.getByLabel("Business outcomes").fill("Confirm the audit reporting workflow.");
  await newBoard.getByRole("button", { name: "Generate storyboard" }).click();
  await page.getByRole("heading", { name: audience, exact: true }).waitFor();

  const brief = page.getByRole("region", { name: "Storyboard brief" });
  const scenes = page.getByRole("region", { name: "Storyboard scenes" });
  const supported = scenes.getByRole("article").filter({ has: page.getByRole("heading", { name: "Report export" }) });
  const approval = page.getByRole("region", { name: "Storyboard approval" });
  const readiness = page.getByRole("region", { name: "Demo readiness" });
  await readiness.getByText("Not demo-ready", { exact: true }).waitFor();
  assert.equal(await readiness.getByRole("link", { name: /Download/ }).count(), 0);
  await scenes.getByText(/Product support is unverified/).waitFor();
  await supported.getByRole("link", { name: "Synthetic release guide" }).waitFor();
  await supported.getByRole("link", { name: "Open requirement revision" }).click();
  await page.waitForURL(/#plan-.*-r1$/);
  await page.getByRole("region", { name: "Revision history" }).getByText("Revision 1 · Approved").waitFor();
  await page.goto(studio);

  const first = await scenes.locator("article h3").first().innerText();
  await page.locator("summary").filter({ hasText: /^Reorder and time scenes$/ }).click();
  await page.getByRole("button", { name: "Move scene 1 down" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("spinbutton", { name: "Minutes for scene 1" }).fill("4");
  assert.equal(await page.getByRole("button", { name: "Save agenda" }).isDisabled(), true);
  await page.getByRole("spinbutton", { name: "Minutes for scene 2" }).fill("7");
  await page.getByRole("button", { name: "Save agenda" }).click();
  await brief.getByText("Draft · Revision 2").waitFor();
  assert.notEqual(await scenes.locator("article h3").first().innerText(), first);
  await supported.locator("summary").filter({ hasText: /^Edit scene$/ }).click();
  const form = supported.getByRole("form", { name: "Edit scene" });
  await form.getByLabel("Talk track").fill(manualTrack);
  await form.getByRole("button", { name: "Save scene" }).click();
  await brief.getByText("Draft · Revision 3").waitFor();
  await supported.getByText(manualTrack, { exact: true }).filter({ visible: true }).waitFor();
  await approval.getByRole("checkbox").check();
  await approval.getByRole("button", { name: "Approve revision" }).click();
  await brief.getByText("Approved · Revision 3").waitFor();
  for (const task of ["Prepare and verify fictional demo data", "Rehearse the flow", "Review demo risks"]) {
    await readiness.getByRole("button", { name: `Mark complete: ${task}` }).click();
    await readiness.getByRole("button", { name: `Reopen: ${task}` }).waitFor();
  }
  await readiness.getByText("Not demo-ready", { exact: true }).waitFor();
  await readiness.getByText(/Full product support is missing/).waitFor();
  const markdownLink = readiness.getByRole("link", { name: "Download Markdown" });
  const [markdown] = await Promise.all([page.waitForEvent("download"), markdownLink.click()]);
  assert.match(markdown.suggestedFilename(), /-r3\.md$/);
  const text = await readFile(await markdown.path(), "utf8");
  assert.ok(text.includes("Not demo-ready") && text.includes(manualTrack));
  assert.ok(text.includes("- [x] Prepare and verify fictional demo data"));
  assert.ok(text.includes(`${config.base}/workspaces/`));
  const pdfLink = readiness.getByRole("link", { name: "Download PDF" });
  exportHref = await pdfLink.getAttribute("href");
  const [pdf] = await Promise.all([page.waitForEvent("download"), pdfLink.click()]);
  assert.match(pdf.suggestedFilename(), /-r3\.pdf$/);
  assert.equal((await readFile(await pdf.path())).subarray(0, 5).toString(), "%PDF-");
}

async function regenerateStoryboard(page) {
  await page.goto(studio);
  const brief = page.getByRole("region", { name: "Storyboard brief" });
  const scene = page.getByRole("region", { name: "Storyboard scenes" }).getByRole("article").filter({
    has: page.getByRole("heading", { name: "Report export" }),
  });
  await scene.getByText(/Stale evidence/).waitFor();
  await scene.getByRole("button", { name: "Preview regeneration" }).click();
  await scene.getByRole("region", { name: "Regeneration proposal" }).getByText(/Mapping r2/).waitFor();
  await scene.getByRole("button", { name: "Apply proposal" }).click();
  await brief.getByText("Draft · Revision 4").waitFor();
  await scene.getByText(manualTrack, { exact: true }).filter({ visible: true }).waitFor();
  await scene.getByText(/Product support is unverified/).waitFor();
  await page.getByRole("link", { name: /Revision 3 · Approved/ }).click();
  await brief.getByText("Historical revision").waitFor();
  assert.equal(await page.getByRole("button", { name: "Preview regeneration" }).count(), 0);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
}

async function verifyCatalogAndMapping(page) {
  await page.goto(catalog);
  await page.locator("summary").filter({ hasText: /^Add product release$/ }).click();
  await page.getByLabel("Product", { exact: true }).fill("Synthetic Audit");
  await page.getByLabel("Version", { exact: true }).fill("2026.1");
  await page.getByRole("button", { name: "Create release" }).click();
  await page.locator("summary").filter({ hasText: /^Add capability$/ }).click();
  const form = page.getByRole("form", { name: "Add capability" });
  await form.getByLabel("Capability name").fill("Report export");
  await form.getByLabel("Support status").selectOption("supported");
  await form.getByLabel("Description").fill("The audit report can be exported on a monthly schedule.");
  await form.getByLabel("Exact requirement phrases").fill(config.statement);
  await form.getByLabel("Document title").fill("Synthetic release guide");
  await form.getByLabel("Section or anchor").fill("Export");
  await form.getByLabel("HTTPS documentation URL").fill("https://docs.example.test/guide#export");
  await form.getByRole("button", { name: "Create capability" }).click();
  const entry = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: "Report export", exact: true }),
  });
  await entry.waitFor();
  await page.getByRole("searchbox", { name: "Search capabilities" }).fill("export");
  await Promise.all([
    page.waitForURL((url) => url.searchParams.get("q") === "export"),
    page.getByRole("button", { name: "Search catalog" }).click(),
  ]);
  await entry.waitFor();

  await page.goto(mappings);
  const mapping = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: config.statement, exact: true }),
  });
  const generate = page.getByRole("button", { name: "Generate mapping drafts" });
  await generate.focus();
  await page.keyboard.press("Enter");
  await mapping.getByText("Draft · Mapping r1", { exact: true }).waitFor();
  await mapping.getByText("Supported", { exact: true }).first().waitFor();
  const source = mapping.getByRole("link", { name: "Synthetic release guide" });
  assert.equal(await source.getAttribute("href"), "https://docs.example.test/guide#export");
  const confirm = mapping.getByRole("button", { name: "Confirm this mapping revision" });
  await confirm.click();
  await mapping.getByText("Reviewed · Mapping r1", { exact: true }).waitFor();
  const unmatched = page.getByRole("article").filter({ has: page.getByRole("heading", { name: unknownRequirement, exact: true }) });
  await unmatched.getByRole("button", { name: "Confirm this mapping revision" }).click();
  await unmatched.getByText("Reviewed · Mapping r1", { exact: true }).waitFor();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await createStoryboard(page);

  await page.goto(catalog);
  await entry.locator("summary").filter({ hasText: /^Edit capability$/ }).click();
  const edit = entry.getByRole("form", { name: "Edit capability" });
  await edit.getByLabel("Support status").selectOption("unknown");
  await edit.getByRole("button", { name: "Save new revision" }).click();
  await entry.getByText("Unknown", { exact: true }).filter({ visible: true }).waitFor();
  await page.goto(mappings);
  await mapping.getByText("Stale catalog evidence", { exact: true }).waitFor();
  await source.waitFor();
  assert.equal(await confirm.count(), 0);
  await mapping.locator("summary").filter({ hasText: /^Edit mapping$/ }).click();
  await mapping.getByRole("combobox", { name: /Catalog evidence/ }).selectOption({ label: "Report export · Unknown · r2" });
  await mapping.getByRole("button", { name: "Save mapping draft" }).click();
  await mapping.getByText("Draft · Mapping r2", { exact: true }).waitFor();
  await confirm.click();
  await mapping.getByText("Reviewed · Mapping r2", { exact: true }).waitFor();
  await regenerateStoryboard(page);
}

try {
  const page = await signIn(config.owner);
  await page.goto(plan.replace(/\/plan$/, ""));
  const consent = page.getByRole("checkbox", { name: /I confirm I have permission to use this source/ });
  await consent.waitFor();
  assert.equal(await consent.isChecked(), false);
  assert.match(await consent.getAttribute("aria-describedby"), /\S+/);
  await page.getByText(/Obtain any required recording consent/).waitFor();
  await consent.focus();
  await page.keyboard.press("Space");
  assert.equal(await consent.isChecked(), true);
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
  await page.locator("summary").filter({ hasText: /^Add requirement$/ }).click();
  const nextRequirement = page.getByRole("form", { name: "Add requirement" });
  await nextRequirement.getByLabel("Requirement").fill(unknownRequirement);
  await nextRequirement.getByLabel("Rationale").fill("Discuss the fictional summary workflow.");
  await nextRequirement.getByRole("button", { name: "Add requirement", exact: true }).click();
  const nextCard = page.getByRole("article").filter({ has: page.getByRole("heading", { name: unknownRequirement, exact: true }) });
  await nextCard.getByRole("button", { name: "Approve this revision" }).click();
  await nextCard.getByText("Approved · Revision 1").waitFor();
  await verifyCatalogAndMapping(page);

  const peer = await signIn(config.peer);
  await peer.goto(plan);
  await peer.getByRole("heading", { name: config.statement, exact: true }).waitFor();
  assert.equal(await peer.getByRole("button", { name: "Generate drafts" }).count(), 0);
  assert.equal(await peer.getByText("Edit item", { exact: true }).count(), 0);
  assert.equal(await peer.getByRole("button", { name: "Approve this revision" }).count(), 0);
  await peer.goto(mappings);
  await peer.getByText("Reviewed · Mapping r2", { exact: true }).waitFor();
  assert.equal(await peer.getByRole("button", { name: "Generate mapping drafts" }).count(), 0);
  assert.equal(await peer.getByText("Edit mapping", { exact: true }).count(), 0);
  await peer.goto(studio);
  await peer.getByRole("heading", { name: audience, exact: true }).waitFor();
  assert.equal(await peer.getByRole("button", { name: "Approve revision" }).count(), 0);
  assert.equal(await peer.getByRole("button", { name: "Preview regeneration" }).count(), 0);

  const outsider = await signIn(config.outsider);
  await outsider.goto(plan);
  await outsider.getByRole("heading", { name: "Opportunity not found" }).waitFor();
  assert.equal(await outsider.getByText(config.statement, { exact: true }).count(), 0);
  await outsider.goto(mappings);
  await outsider.getByRole("heading", { name: "Opportunity not found" }).waitFor();
  assert.equal(await outsider.getByText(config.statement, { exact: true }).count(), 0);
  await outsider.goto(studio);
  await outsider.getByRole("heading", { name: "Opportunity not found" }).waitFor();
  assert.equal(await outsider.getByText(audience, { exact: true }).count(), 0);
  assert.ok(exportHref);
  assert.equal((await outsider.request.get(new URL(exportHref, config.base).href)).status(), 404);
  console.log("Planning, catalog, Demo Studio and storyboard download browser checks passed.");
} finally {
  await browser.close();
}
