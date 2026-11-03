/**
 * Optional end-to-end smoke test of the running application in a real browser (Playwright + Chromium).
 *
 * It is NOT part of `npm test`. It drives the UI against a live API and CREATES DATA (a dataset, an analysis job,
 * a review, a viewer account), so run it only against a disposable development database — never production.
 *
 * Prerequisites:
 *   - API running with at least one approved model whose schema matches the CSV, and an administrator account
 *   - Frontend running (`npm run dev`), or set E2E_BASE_URL to wherever it is served
 *   - `npx playwright install chromium` (once), or E2E_CHROMIUM_PATH pointing at a Chromium binary
 *
 * Environment:
 *   E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD   administrator credentials (required)
 *   E2E_CSV                               flow CSV to upload, ideally containing attack traffic (required)
 *   E2E_BASE_URL                          default http://localhost:5173
 *   E2E_OUTPUT_DIR                        screenshots, default ./e2e-output
 *   E2E_CHROMIUM_PATH                     optional browser executable
 *
 *   npm run e2e:smoke
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright";

const BASE = (process.env.E2E_BASE_URL ?? "http://localhost:5173").replace(/\/$/, "");
const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD;
const CSV = process.env.E2E_CSV;
const OUT = process.env.E2E_OUTPUT_DIR ?? "e2e-output";

if (!ADMIN_EMAIL || !ADMIN_PASSWORD || !CSV) {
  console.error("Set E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD and E2E_CSV (see the header of e2e/smoke.mjs).");
  process.exit(2);
}
mkdirSync(`${OUT}/shots`, { recursive: true });

const runId = Date.now().toString(36);
const viewerEmail = `viewer-${runId}@example.org`;
// Random throw-away password that satisfies the default policy (length, letters and digits).
const viewerPassword = `Rv-${randomBytes(12).toString("base64url")}-7q`;
const csvHead = readFileSync(CSV, "utf8").split(/\r?\n/).slice(0, 4).join("\n");

const browser = await chromium.launch(process.env.E2E_CHROMIUM_PATH ? { executablePath: process.env.E2E_CHROMIUM_PATH } : {});
const results = [];
const consoleErrors = [];
const apiErrors = [];

function watch(page, tag) {
  page.on("pageerror", (error) => consoleErrors.push(`${tag} pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) consoleErrors.push(`${tag}: ${message.text()}`);
  });
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 400) {
      apiErrors.push(`${tag} ${response.status()} ${response.request().method()} ${response.url().replace(BASE, "")}`);
    }
  });
}

class Skip extends Error {}

async function step(page, name, fn) {
  try {
    await fn();
    results.push(["PASS", name]);
  } catch (error) {
    const skipped = error instanceof Skip;
    results.push([skipped ? "SKIP" : "FAIL", `${name}${error.message ? ` — ${error.message.split("\n")[0]}` : ""}`]);
    if (!skipped) await page.screenshot({ path: `${OUT}/shots/fail-${name.replace(/\W+/g, "-")}.png`, fullPage: true }).catch(() => {});
  }
}

const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const page = await context.newPage();
watch(page, "admin");
const shot = (name) => page.screenshot({ path: `${OUT}/shots/${name}.png`, fullPage: true });
let jobUrl = null;

await step(page, "anonymous visitors are sent to sign-in", async () => {
  await page.goto(`${BASE}/alerts`);
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
});
await step(page, "administrator signs in and returns to the requested page", async () => {
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(`${BASE}/alerts`);
});
await step(page, "dataset upload: local preview, server validation", async () => {
  await page.goto(`${BASE}/datasets/upload`);
  await page.locator("input[type=file]").setInputFiles(CSV);
  await page.getByRole("heading", { name: "Local preview" }).waitFor();
  await page.getByRole("button", { name: "Upload and validate" }).click();
  const validated = page.getByText("Validation passed");
  const duplicate = page.getByText("An identical dataset has already been uploaded.");
  await validated.or(duplicate).waitFor({ timeout: 120_000 });
  await shot("upload");
});
await step(page, "re-uploading the same file is rejected as a duplicate", async () => {
  await page.goto(`${BASE}/datasets/upload`);
  await page.locator("input[type=file]").setInputFiles(CSV);
  await page.getByRole("button", { name: "Upload and validate" }).click();
  await page.getByText("An identical dataset has already been uploaded.").waitFor({ timeout: 60_000 });
});
await step(page, "start an analysis with an approved model", async () => {
  await page.goto(`${BASE}/datasets`);
  await page.getByRole("button", { name: "Analyze" }).first().click();
  const dialog = page.getByRole("dialog", { name: "New analysis job" });
  const model = dialog.getByLabel("Model");
  await model.locator("option").nth(1).waitFor({ state: "attached", timeout: 30_000 });
  await model.selectOption({ index: 1 });
  await dialog.getByRole("button", { name: "Start analysis" }).click();
  await page.waitForURL(/\/analyses\/[0-9a-f-]{36}$/);
  jobUrl = page.url();
});
await step(page, "the job completes and results render", async () => {
  if (!jobUrl) throw new Skip("no job");
  await page.getByRole("heading", { name: "Predictions" }).waitFor({ timeout: 15 * 60_000 });
  await shot("results");
});
await step(page, "filters update the URL and CSV export downloads", async () => {
  if (!jobUrl) throw new Skip("no job");
  await page.getByLabel("Alerts only").check();
  await page.getByLabel("Minimum risk").fill("50");
  if (!/alerts=true/.test(page.url()) || !/min_risk=50/.test(page.url())) throw new Error(`filters missing from URL: ${page.url()}`);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "CSV" }).click()]);
  const header = readFileSync(await download.path(), "utf8").split("\n")[0];
  if (!header.includes("risk_score")) throw new Error(`unexpected export header: ${header.slice(0, 120)}`);
});
await step(page, "open a prediction and record a review", async () => {
  if (!jobUrl) throw new Skip("no job");
  await page.goto(jobUrl);
  await page.locator("table tbody tr.clickable").first().click();
  await page.getByRole("heading", { name: "Analyst review" }).waitFor();
  await page.getByLabel("Disposition").selectOption("needs_investigation");
  await page.getByLabel("Notes").fill(`E2E smoke test ${runId}`);
  await page.getByRole("button", { name: "Record review" }).click();
  await page.getByText("Review recorded.").waitFor();
  await shot("prediction");
});
await step(page, "alerts list and alert details", async () => {
  await page.goto(`${BASE}/alerts`);
  await page.getByRole("heading", { name: "Alerts", exact: true }).waitFor();
  const rows = page.locator("table tbody tr.clickable");
  await rows.first().waitFor({ timeout: 10_000 }).catch(() => {});
  if ((await rows.count()) === 0) throw new Skip("no alerts were produced");
  await rows.first().click();
  await page.getByRole("heading", { name: "Explanation" }).waitFor();
  await shot("alert");
});
await step(page, "quick analysis of pasted CSV rows", async () => {
  await page.goto(`${BASE}/analyses?tab=quick`);
  const model = page.getByLabel("Approved model");
  await model.locator("option").nth(1).waitFor({ state: "attached" });
  await model.selectOption({ index: 1 });
  await page.getByLabel("Flow records").fill(csvHead);
  await page.getByRole("button", { name: /^Analyze \d+ record/ }).click();
  await page.getByRole("heading", { name: "Results" }).waitFor({ timeout: 60_000 });
});
await step(page, "model artifacts verify", async () => {
  await page.goto(`${BASE}/models`);
  await page.locator("table tbody tr.clickable").first().click();
  await page.getByRole("button", { name: "Verify artifacts" }).click();
  await page.getByText("All integrity checks passed").waitFor({ timeout: 120_000 });
});
await step(page, "analytics report download", async () => {
  await page.goto(`${BASE}/analytics`);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Report CSV" }).click()]);
  if (!download.suggestedFilename().endsWith(".csv")) throw new Error(download.suggestedFilename());
});
await step(page, "administrator creates a viewer account", async () => {
  await page.goto(`${BASE}/admin/users`);
  await page.getByRole("button", { name: "Create user" }).click();
  const dialog = page.getByRole("dialog", { name: "Create user" });
  await dialog.getByLabel("Email").fill(viewerEmail);
  await dialog.getByLabel("Display name").fill(`E2E viewer ${runId}`);
  await dialog.getByLabel("Role").selectOption("viewer");
  await dialog.getByLabel("Initial password").fill(viewerPassword);
  await dialog.getByLabel("Confirm password").fill(viewerPassword);
  await dialog.getByRole("button", { name: "Create user" }).click();
  await dialog.waitFor({ state: "detached" });
});
await step(page, "audit log records the session", async () => {
  await page.goto(`${BASE}/admin/audit-logs`);
  await page.locator("table").getByText("auth.login.success").first().waitFor();
});
await step(page, "session survives a reload; sign-out protects pages", async () => {
  await page.goto(`${BASE}/`);
  await page.reload();
  await page.getByRole("heading", { name: "Security overview" }).waitFor();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
  await page.goto(`${BASE}/datasets`);
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
});

const viewerPage = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
watch(viewerPage, "viewer");
await step(viewerPage, "viewer sees aggregates only", async () => {
  await viewerPage.goto(`${BASE}/login`);
  await viewerPage.getByLabel("Email").fill(viewerEmail);
  await viewerPage.getByLabel("Password").fill(viewerPassword);
  await viewerPage.getByRole("button", { name: "Sign in" }).click();
  await viewerPage.getByRole("heading", { name: "Security overview" }).waitFor();
  const nav = viewerPage.getByRole("complementary", { name: "Primary" });
  if (await nav.getByRole("link", { name: "Datasets" }).count()) throw new Error("viewer can see the Datasets link");
  await viewerPage.goto(`${BASE}/alerts`);
  await viewerPage.getByText("You do not have access to this page").waitFor();
});

await browser.close();
for (const [status, name] of results) console.log(`${status}  ${name}`);
console.log(`\nUnexpected console errors: ${consoleErrors.length ? `\n  ${consoleErrors.join("\n  ")}` : "none"}`);
console.log(`API responses >= 400 (a 401 from /auth/refresh on first visit and the duplicate-upload 409 are expected):`);
console.log(apiErrors.length ? `  ${apiErrors.join("\n  ")}` : "  none");
console.log(`\nTest account created: ${viewerEmail} (deactivate it in User management when done).`);
process.exit(results.some(([status]) => status === "FAIL") ? 1 : 0);
