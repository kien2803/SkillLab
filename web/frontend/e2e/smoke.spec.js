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
