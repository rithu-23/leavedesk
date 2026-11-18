import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright end-to-end tests (UI_SPEC.md §11). They drive a real browser against the whole
 * system running in Docker: `docker compose up -d --build --wait`, then `npm run e2e`.
 *
 * - E2E_BASE_URL: where the app runs (default: the Docker web service on port 8080).
 * - DEMO_PASSWORD: the demo users' password; read from ../.env when not set.
 * - CHROME_PATH: optional path to an installed Chrome, instead of Playwright's own browser.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1, // the tests share one database, so they run one at a time
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env['CHROME_PATH']
      ? { executablePath: process.env['CHROME_PATH'], args: ['--no-sandbox'] }
      : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
