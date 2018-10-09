import { getAgentRoute } from '@/core/constants/agent-routes';

import { expect, mockData, test } from './fixtures';

test.describe('SearchInput - Query Param Syncing', () => {
  test('syncs search value to URL query param', async ({ mockedPage }) => {
    await mockedPage.goto('/');

    const searchInput = mockedPage.getByPlaceholder('Search agents...');

    // Type in search input
    await searchInput.fill('Customer');

    // Wait for debounced URL update (300ms)
    await mockedPage.waitForTimeout(350);

    // Verify URL has the query param
    await expect(mockedPage).toHaveURL(/.*\?search=Customer/);
  });

  test('reads search value from URL query param on page load', async ({
    mockedPage,
  }) => {
    // Navigate with query param
    await mockedPage.goto('/?search=Customer');

    // Wait for API response with the search filter
    await mockedPage.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/agents') &&
        response.url().includes('name=Customer') &&
        response.status() === 200
    );

    // Wait for page to load
    await expect(mockedPage.getByRole('table')).toBeVisible();

    // Verify search input has the value from URL
    const searchInput = mockedPage.getByPlaceholder('Search agents...');
    await expect(searchInput).toHaveValue('Customer');

    // Verify filtered results are shown
    await expect(mockedPage.getByText('customer-support-bot')).toBeVisible();
  });

  test('clear button removes query param from URL', async ({ mockedPage }) => {
    await mockedPage.goto('/?search=Customer');

    // Wait for page to load
    await expect(mockedPage.getByRole('table')).toBeVisible();

    const searchInput = mockedPage.getByPlaceholder('Search agents...');
    await expect(searchInput).toHaveValue('Customer');

    // Find and click the clear button (X icon)
    const clearButton = mockedPage.getByTestId('search-clear-search');
    await clearButton.click();

    // Wait for URL update
    await mockedPage.waitForTimeout(100);

    // Verify query param is removed from URL
    await expect(mockedPage).toHaveURL(/\/(\?|$)/); // URL should not have search param

    // Verify search input is cleared
    await expect(searchInput).toHaveValue('');

    // Verify all agents are shown again
    for (const agent of mockData.agents.agents) {
      await expect(mockedPage.getByText(agent.agent_name)).toBeVisible();
    }
  });

  test('preserves search state on browser back/forward', async ({
