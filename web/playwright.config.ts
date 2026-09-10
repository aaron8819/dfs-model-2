import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 60000,
  reporter: [["list"], ["json", { outputFile: "../artifacts/increment2-browser.json" }]],
  use: {
    baseURL: "http://127.0.0.1:8765",
    viewport: { width: 1440, height: 1100 },
    screenshot: "only-on-failure",
    trace: "off",
  },
});
