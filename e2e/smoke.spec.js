import { test, expect } from "@playwright/test";

test("overview renders real lab stats", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("SkillLab")).toBeVisible();
  await expect(page.getByText("projects")).toBeVisible();
});

test("nav + projects page lists demo projects", async ({ page }) => {
  await page.goto("/projects");
  await expect(page.getByText("commit-helper-research")).toBeVisible();
});

test("skills page shows registry", async ({ page }) => {
  await page.goto("/skills");
  await expect(page.getByText("commit-helper").first()).toBeVisible();
});

test("auth gate: write without token is rejected", async ({ page }) => {
  const r = await page.request.post("/api/v1/projects",
    { data: { id: "e2e-x" } });
  expect(r.status()).toBe(401);
});

const RUN = "exp-trigger-wording--good-desc--write-commit-msg--r0";

test("run detail shows eval + artifacts + transcript", async ({ page }) => {
  await page.goto(`/runs/${RUN}`);
  await expect(page.getByText("Evaluation")).toBeVisible();
  await expect(page.getByText("OUTPUT.md").first()).toBeVisible();
  await page.getByText(/^Transcript/).click();
  await expect(page.getByText("#0 system")).toBeVisible();
});

test("compare endpoint returns arm x task matrix", async ({ page }) => {
  const r = await page.request.get(
    "/api/v1/experiments/exp-trigger-wording/compare");
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.tasks).toContain("write-commit-msg");
  expect(j.arms.map((a) => a.name)).toContain("control");
});

test("run detail 404 for unknown run", async ({ page }) => {
  const r = await page.request.get("/api/v1/runs/no-such-run");
  expect(r.status()).toBe(404);
});

test("knowledge page lists insights + principles", async ({ page }) => {
  await page.goto("/knowledge");
  await expect(page.getByText("specific-trigger-descriptions"))
    .toBeVisible();
  await expect(page.getByText("[principle]")).toBeVisible();
});

test("regressions page shows stored verdicts", async ({ page }) => {
  await page.goto("/regressions");
  await expect(page.getByText("reg-commit-helper-v1-v2-bad-01"))
    .toBeVisible();
  const r = await page.request.get(
    "/api/v1/regressions/reg-commit-helper-v1-v2-bad-01");
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.report.verdict).toBe("regressed");
  expect(j.report.counts.activation).toBe(1);
});

test("release detail carries computed checklist", async ({ page }) => {
  const r = await page.request.get(
    "/api/v1/releases/commit-helper/1.0.0");
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.release.status).toBe("released");
  const ids = j.checklist.map((c) => c.id);
  expect(ids).toContain("evaluated-evidence");
  expect(j.checklist.every((c) => c.ok)).toBeTruthy();
});

test("write gates on lifecycle endpoints", async ({ page }) => {
  for (const [method, url, data] of [
    ["post", "/api/v1/insights", { title: "x" }],
    ["post", "/api/v1/regressions",
     { skill: "s", baseline: "a", candidate: "b" }],
    ["post", "/api/v1/releases", { skill: "s", version: "1",
                                   variant: "v" }],
    ["post", "/api/v1/releases/s/1/status", { status: "released" }],
    ["post", "/api/v1/insights/x/confirm", {}],
  ]) {
    const r = await page.request[method](url, { data });
    expect(r.status()).toBe(401);
  }
});
