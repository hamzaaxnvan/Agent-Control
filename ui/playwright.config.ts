import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright integration test configuration
 * These tests run against the frontend with mocked API responses.
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './tests',
  /* Component tests use playwright-ct.config.ts (Vite + mount). */
  testIgnore: '**/ct/**',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Use 2 workers in CI for faster execution (GitHub Actions runners have 2-4 cores).
   * Use default (CPU cores) locally for maximum speed.
   */
  workers: process.env.CI ? 2 : undefined,
  /* Reporter to use */
  reporter: [['html', { open: 'never' }], ['list']],
