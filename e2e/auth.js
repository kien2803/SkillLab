// Auth helper: every spec seeds the bearer token into localStorage
// before app scripts run AND attaches the Authorization header to the
// Playwright request context (page.request.* doesn't read localStorage).
// Token "t" matches the playwright webServer env.
import { test } from "@playwright/test";

export function authed() {
  test.use({ extraHTTPHeaders: { Authorization: "Bearer t" } });
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((t) =>
      localStorage.setItem("skilllab_token", t), "t");
  });
}
