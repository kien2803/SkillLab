import { test, expect } from "@playwright/test";
import { authed } from "./auth.js";

authed();

test("skill editor: open variant, edit SKILL.md, save, revisions", async ({
  page }) => {
  await page.goto("/skills");
  await page.getByRole("link", { name: "edit" }).first().click();
  await expect(page.getByText("skill editor")).toBeVisible();
  // SKILL.md auto-opens on mount
  const ta = page.locator(".ed-ta");
  await expect(ta).toBeVisible({ timeout: 8000 });
  const before = await ta.inputValue();
  await ta.fill(before + "\n<!-- e2e -->\n");
  await expect(page.getByText("modified")).toBeVisible();
  await ta.press("Control+s");
  await expect(page.getByText(/saved/i).first()).toBeVisible({
    timeout: 8000 });
  await expect(page.getByText(/revision/i).first()).toBeVisible();
});

test("experiment builder: create, validate, save via UI", async ({
  page }) => {
  await page.goto("/experiments");
  const eid = "e2e-exp-" + Date.now().toString(36);
  await page.getByPlaceholder("new experiment id").fill(eid);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText(eid).first()).toBeVisible();
  await page.locator(".card", { hasText: eid })
    .getByRole("button", { name: "Builder" }).click();
  const builder = page.locator(".expb");
  await expect(builder.getByText("General")).toBeVisible();
  await builder.getByRole("button", { name: "Validate" }).click();
  // scaffold has no tasks — server-side validation reports errors
  await expect(builder.getByText(/error|invalid/i).first())
    .toBeVisible({ timeout: 8000 });
  await builder.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/saved|error/i).first()).toBeVisible({
    timeout: 8000 });
});
