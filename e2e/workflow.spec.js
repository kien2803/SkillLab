import { test, expect } from "@playwright/test";
import { authed } from "./auth.js";

authed();

// The agency-user journey: Home → Skills → Test Suite → Benchmark
// → Report. Each module reachable from the rail, content real.
test("four modules reachable from rail", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Skills" }).click();
  await expect(page.getByText("Skill Management")).toBeVisible();
  await page.getByRole("link", { name: "Test Suite" }).click();
  await expect(page).toHaveURL(/\/suite/);
  await expect(page.getByText("Test Suite")).toBeVisible();
  await page.getByRole("link", { name: "Benchmark" }).click();
  await expect(page.getByText("New benchmark")).toBeVisible();
  await expect(page.getByText("Run regression")).toBeVisible();
  await page.getByRole("link", { name: "Report" }).click();
  await expect(page.getByRole("heading",
    { name: "Quality Report" })).toBeVisible();
});

test("benchmark launcher requires selections", async ({ page }) => {
  await page.goto("/benchmark");
  const btn = page.getByRole("button", { name: "Run benchmark" });
  await expect(btn).toBeDisabled();
});

test("quality report renders verdict + export for v3-bp", async ({
  page }) => {
  await page.goto("/report");
  await page.getByRole("combobox").selectOption("commit-helper@v3-bp");
  await expect(page.getByText(/validated|improved|insufficient|neutral/)
    .first()).toBeVisible({ timeout: 8000 });
  await expect(page.getByRole("button", { name: "Export .md" }))
    .toBeVisible();
});

test("step cards link into the workflow", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Run benchmark/ }).click();
  await expect(page).toHaveURL(/\/benchmark/);
});
