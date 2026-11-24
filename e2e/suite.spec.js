import { test, expect } from "@playwright/test";
import { authed } from "./auth.js";

authed();

// FLOW A — create a test case through the UI, reopen it, verify persisted
test("suite flow A: create + reopen a task", async ({ page }) => {
  await page.goto("/suite");
  await page.getByPlaceholder("new task id").fill("e2e-task");
  await page.getByRole("button", { name: "+", exact: true }).click();
  await expect(page.getByRole("heading", { name: "e2e-task" }))
    .toBeVisible();
  // editor opens with the new task — error for empty prompt is flagged
  await page.getByRole("button", { name: "input" }).click();
  await page.locator(".tsed-body textarea").fill(
    "Write OUTPUT.md summarizing the staged diff.");
  await page.getByRole("button", { name: "save task" }).click();
  await expect(page.getByText("saved")).toBeVisible();
  // reopen — values persisted
  await page.reload();
  await page.getByRole("button", { name: "e2e-task" }).click();
  await page.getByRole("button", { name: "input" }).click();
  await expect(page.locator(".tsed-body textarea")).toHaveValue(
    /OUTPUT\.md/);
});

// FLOW B — edit prompt + evaluation and verify
test("suite flow B: edit prompt + evaluation", async ({ page }) => {
  await page.goto("/suite");
  await page.getByRole("button", { name: "write-commit-msg" }).click();
  await page.getByRole("button", { name: "input" }).click();
  const ta = page.locator(".tsed-body textarea");
  const before = await ta.inputValue();
  await ta.fill(before + "\nAlso mention the --retry flag.");
  await page.getByRole("button", { name: "evaluation" }).click();
  await page.getByRole("button", { name: "+ add check" }).click();
  await expect(page.locator(".check-row")).toHaveCount(2);
  await page.getByRole("button", { name: "save task" }).click();
  await expect(page.getByText("saved")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "write-commit-msg" }).click();
  await page.getByRole("button", { name: "input" }).click();
  await expect(page.locator(".tsed-body textarea"))
    .toHaveValue(/--retry flag/);
});

// FLOW C — duplicate then archive; original intact
test("suite flow C: duplicate + delete", async ({ page }) => {
  await page.goto("/suite");
  await page.getByRole("button", { name: "unrelated-refactor" }).click();
  page.once("dialog", (d) => d.accept("refactor-copy"));
  await page.getByRole("button", { name: "duplicate" }).click();
  await expect(page.getByRole("button", { name: "refactor-copy" }))
    .toBeVisible();
  await page.getByRole("button", { name: "refactor-copy" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "archive" }).click();
  await expect(page.getByRole("button", { name: "refactor-copy" }))
    .toHaveCount(0);
  await expect(page.getByRole("button", { name: "unrelated-refactor" }))
    .toBeVisible();
});

// FLOW D — rubric management
test("suite flow D: rubric create + criteria", async ({ page }) => {
  await page.goto("/suite");
  await page.getByRole("button", { name: "rubrics" }).click();
  await page.getByPlaceholder("new rubric id").fill("e2e-rubric");
  await page.getByRole("button", { name: "+", exact: true }).click();
  await expect(page.getByRole("heading", { name: "e2e-rubric" }))
    .toBeVisible();
  await page.getByRole("button", { name: "+ add criterion" }).click();
  await page.locator(".crit-row input").first().fill("output-exists");
  await page.locator(".crit-row select").selectOption("deterministic");
  await page.locator(".crit-row .ts-grid input").fill("out.md");
  await page.getByRole("button", { name: "save rubric" }).click();
  await expect(page.getByText("saved")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "rubrics" }).click();
  await page.getByRole("button", { name: "e2e-rubric" }).click();
  await expect(page.locator(".crit-row input").first())
    .toHaveValue("output-exists");
});

// FLOW E — benchmark integration: suite feeds the launcher
test("suite flow E: suite -> benchmark selection", async ({ page }) => {
  // create a named suite over the runnable tasks via the API
  await page.request.post("/api/v1/suites", {
    headers: { Authorization: "Bearer t" },
    data: { id: "e2e-suite", tasks: ["write-commit-msg",
                                     "unrelated-refactor"] } });
  await page.goto("/benchmark");
  const suiteSel = page.locator("select", { hasText: "suite…" });
  await expect(suiteSel).toBeVisible();
  await suiteSel.selectOption("e2e-suite");
  await expect(page.getByText("2 selected")).toBeVisible();
});

// FLOW F — invalid task blocked from suite + flagged in validation
test("suite flow F: invalid task surfaces + blocks", async ({ page }) => {
  await page.request.post("/api/v1/tasks", {
    headers: { Authorization: "Bearer t" },
    data: { id: "broken-task", kind: "performance", prompt: "" } });
  await page.goto("/suite");
  await page.getByRole("button", { name: "show" }).click();
  await expect(page.getByText("prompt is empty")).toBeVisible();
  await page.locator(".nav-item", { hasText: "broken-task" }).click();
  await expect(page.getByText("not runnable").first()).toBeVisible();
});
