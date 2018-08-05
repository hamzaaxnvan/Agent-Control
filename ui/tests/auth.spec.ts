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
      page.getByRole('heading', { name: 'Agent Control' })
    ).toBeVisible();
    await expect(
      page.getByText('Enter your API key to continue.')
    ).toBeVisible();
    await expect(page.getByPlaceholder('Enter your API key')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();

    // Main app content should not be visible
    await expect(
      page.getByRole('heading', { name: 'Agents overview' })
    ).not.toBeVisible();
  });
