import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:8320" },
  webServer: {
    command: "SKILLLAB_DIR=examples/demo-lab SKILLLAB_TOKEN=t " +
             ".venv/bin/uvicorn web.backend.app:app --port 8320",
    url: "http://localhost:8320/api/v1/health",
    reuseExistingServer: true,
    timeout: 30000,
  },
});
