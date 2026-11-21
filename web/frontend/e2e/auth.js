// Auth helper: every spec seeds the bearer token into localStorage
// before app scripts run — mirrors a signed-in session (token "t"
// matches the playwright webServer env).
import { test } from "@playwright/test";

export function authed() {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((t) =>
      localStorage.setItem("skilllab_token", t), "t");
  });
}
