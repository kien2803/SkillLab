import { test, expect } from "@playwright/test";

const errors = [];
test.beforeEach(({ page }) => {
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + e.message));
  page.on("console", (m) => m.type() === "error" &&
    errors.push("CONSOLE: " + m.text()));
});

test("skills interactions", async ({ page }) => {
  await page.goto("/skills");
  await page.getByRole("link", { name: "check" }).first().click();
  await page.waitForTimeout(500);
  await page.getByRole("link", { name: "trace" }).first().click();
  await expect(page.getByText(/Trace:/)).toBeVisible();
  await page.getByRole("button", { name: "Graduation" }).first().click();
  await expect(page.getByText(/Graduation · commit-helper/)).toBeVisible();
  await page.getByRole("button", { name: "Scan agent dirs" }).click();
  await expect(page.getByText("Discovered skills")).toBeVisible();
});

test("blueprint interactions", async ({ page }) => {
  await page.goto("/blueprints");
  await page.getByRole("button",
    { name: "commit-helper-research" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Validate" }).first().click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Revisions" }).first().click();
  await expect(page.getByText(/r1 \[/)).toBeVisible();
});

test("experiments interactions", async ({ page }) => {
  await page.goto("/experiments");
  await page.getByRole("button", { name: "Validate" }).first().click();
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "Runs", exact: true })
    .first().click();
  await page.waitForTimeout(400);
});

test("knowledge + regressions + failures + workspace",
     async ({ page }) => {
  await page.goto("/knowledge"); await page.waitForTimeout(400);
  await page.goto("/regressions"); await page.waitForTimeout(400);
  await page.goto("/failures"); await page.waitForTimeout(400);
  await page.goto("/workspace");
  await expect(page.getByText(/Tasks \(/)).toBeVisible();
});

test("no console errors anywhere", () => {
  expect(errors).toEqual([]);
});
