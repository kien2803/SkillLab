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
    ["post", "/api/v1/projects/p/status", { status: "active" }],
    ["post", "/api/v1/projects/p/questions/q/status",
     { status: "answered" }],
    ["post", "/api/v1/projects/p/decisions", { decision: "d" }],
    ["post", "/api/v1/projects/p/blueprints", { id: "b" }],
    ["post", "/api/v1/skills", { id: "s" }],
    ["post", "/api/v1/skills/import", { src: "/tmp/x" }],
    ["post", "/api/v1/experiments", { id: "e" }],
    ["post", "/api/v1/experiments/e/rerun", {}],
    ["post", "/api/v1/experiments/e/conclude", { conclusion: "c" }],
    ["post", "/api/v1/failures/r/candidate", { variant: "v" }],
    ["post", "/api/v1/proposals/p/reject", {}],
    ["post", "/api/v1/export", { name: "p" }],
    ["post", "/api/v1/import", { src: "/tmp/x" }],
    ["post", "/api/v1/tasks", { id: "t" }],
    ["post", "/api/v1/rubrics", { id: "r" }],
  ]) {
    const r = await page.request[method](url, { data });
    expect(r.status()).toBe(401);
  }
});

test("project detail exposes all entity kinds", async ({ page }) => {
  const r = await page.request.get(
    "/api/v1/projects/commit-helper-research");
  const j = await r.json();
  for (const k of ["meta", "questions", "findings", "sources",
                   "decisions", "notes"])
    expect(j).toHaveProperty(k);
});

test("blueprint validate + revisions endpoints", async ({ page }) => {
  const v = await page.request.get(
    "/api/v1/projects/commit-helper-research/blueprints/" +
    "commit-helper-v2/validate");
  expect(v.ok()).toBeTruthy();
  const r = await page.request.get(
    "/api/v1/projects/commit-helper-research/blueprints/" +
    "commit-helper-v2/revisions");
  const revs = await r.json();
  expect(revs.length).toBeGreaterThan(5);
  expect(revs.at(-1).rev).toBeGreaterThan(5);
});

test("lab status + tasks + graduation + validate endpoints",
     async ({ page }) => {
  const st = await (await page.request.get("/api/v1/status")).json();
  expect(st.model).toBe("mock");
  expect(st.runs).toBeGreaterThan(40);
  const tasks = await (await page.request.get("/api/v1/tasks")).json();
  expect(tasks.length).toBeGreaterThan(2);
  const g = await (await page.request.get(
    "/api/v1/skills/commit-helper/graduation")).json();
  expect(g.skill_id).toBe("commit-helper");
  const v = await (await page.request.get(
    "/api/v1/experiments/exp-trigger-wording/validate")).json();
  expect(v.valid).toBeTruthy();
});

test("experiment runs + run diff endpoints", async ({ page }) => {
  const runs = await (await page.request.get(
    "/api/v1/experiments/exp-trigger-wording/runs")).json();
  expect(runs.length).toBeGreaterThan(10);
  const d = await (await page.request.get(
    "/api/v1/diff/exp-trigger-wording--control--write-commit-msg--r0" +
    "/exp-trigger-wording--good-desc--write-commit-msg--r0")).json();
  expect(d).toHaveProperty("transcript_diff");
  expect(d).toHaveProperty("added");
});

test("projects page detail renders entity sections", async ({ page }) => {
  await page.goto("/projects");
  await page.getByText("commit-helper-research").first().click();
  await expect(page.getByText(/Questions \(/)).toBeVisible();
  await expect(page.getByText(/Sources \(/)).toBeVisible();
  await expect(page.getByText(/Decisions \(/)).toBeVisible();
});

test("workspace page lists tasks + rubrics", async ({ page }) => {
  await page.goto("/workspace");
  await expect(page.getByText(/Tasks \(/)).toBeVisible();
  await expect(page.getByText(/Rubrics \(/)).toBeVisible();
  await expect(page.getByText("write-commit-msg")).toBeVisible();
  const r = await page.request.get("/api/v1/rubrics");
  expect(r.ok()).toBeTruthy();
  expect(Array.isArray(await r.json())).toBeTruthy();
  const ts = await (await page.request.get("/api/v1/tasks")).json();
  expect(ts.map((t) => t.id)).toContain("write-commit-msg");
});
