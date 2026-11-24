import { defineConfig } from "@playwright/test";
// ONE e2e suite, kept at the repo root (../../e2e). It runs against a
// disposable copy of the demo lab — specs may write (editor saves,
// experiments) without mutating examples/demo-lab.
export default defineConfig({
  testDir: "../../e2e",
  use: { baseURL: "http://localhost:8320" },
  webServer: {
    command: "cd ../.. && rm -rf /tmp/skilllab-e2e-lab && " +
             "cp -r examples/demo-lab /tmp/skilllab-e2e-lab && " +
             "SKILLLAB_DIR=/tmp/skilllab-e2e-lab SKILLLAB_TOKEN=t " +
             ".venv/bin/uvicorn web.backend.app:app --port 8320",
    url: "http://localhost:8320/api/v1/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
