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
