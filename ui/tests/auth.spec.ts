import {
  expect,
  mockApiRoutesWithAuthRequired,
  mockRoutes,
  test,
} from './fixtures';

test.describe('API key login flow', () => {
  test('shows login modal when server requires API key', async ({ page }) => {
    await mockApiRoutesWithAuthRequired(page);
    await page.goto('/');

    await expect(
