import type { ListAgentsResponse } from '@/core/api/types';
import { getAgentRoute } from '@/core/constants/agent-routes';

import { expect, mockData, mockRoutes, test } from './fixtures';

test.describe('Home Page - Agents Overview', () => {
  test('displays the page header correctly', async ({ mockedPage }) => {
    await mockedPage.goto('/');

    // Check page title
    await expect(
      mockedPage.getByRole('heading', { name: 'Agents overview' })
    ).toBeVisible();

    // Check subtitle
    await expect(
      mockedPage.getByText(
        'Monitor activity and control health across all deployed agents.'
      )
    ).toBeVisible();

    // Check search input exists
    await expect(mockedPage.getByPlaceholder('Search agents...')).toBeVisible();
  });

  test('filters agents when searching', async ({ mockedPage }) => {
    await mockedPage.goto('/');

    // Wait for the table to load
    await expect(mockedPage.getByRole('table')).toBeVisible();

    // All agents should be visible initially
    for (const agent of mockData.agents.agents) {
      await expect(mockedPage.getByText(agent.agent_name)).toBeVisible();
    }

    // Type in the search box to filter
    const searchInput = mockedPage.getByPlaceholder('Search agents...');
    await searchInput.fill('Customer');

    // Wait for debounced search (300ms) and API response
    await mockedPage.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/agents') &&
        response.url().includes('name=Customer') &&
        response.status() === 200
    );

    // Only the matching agent should be visible
    await expect(mockedPage.getByText('customer-support-bot')).toBeVisible();

    // Non-matching agents should be hidden
    await expect(mockedPage.getByText('data-analysis-agent')).not.toBeVisible();
    await expect(
      mockedPage.getByText('code-review-assistant')
    ).not.toBeVisible();

    // Clear search to show all agents again
    await searchInput.clear();

    // Wait for debounced URL update (300ms)
    await mockedPage.waitForTimeout(350);

    // Wait for a previously hidden agent to become visible (confirms filter was cleared)
    // This is more reliable than waiting for an API response that might not happen
    await expect(mockedPage.getByText('data-analysis-agent')).toBeVisible({
      timeout: 5000,
    });

    // Verify all agents are shown again
    for (const agent of mockData.agents.agents) {
      await expect(mockedPage.getByText(agent.agent_name)).toBeVisible();
    }
  });

  test('displays the agents table with data', async ({ mockedPage }) => {
    await mockedPage.goto('/');

    // Wait for the table to load
    await expect(mockedPage.getByRole('table')).toBeVisible();

    // Check table headers
    await expect(
      mockedPage.getByRole('columnheader', { name: 'Agent name' })
    ).toBeVisible();
    await expect(
      mockedPage.getByRole('columnheader', { name: 'Active controls' })
    ).toBeVisible();

    // Check that agents from mock data are displayed
    for (const agent of mockData.agents.agents) {
      await expect(mockedPage.getByText(agent.agent_name)).toBeVisible();
    }
  });

  test('shows loading state initially', async ({ page }) => {
    await mockRoutes.config(page);
    // Set up a delayed API response with proper type
    const delayedResponse: ListAgentsResponse = mockData.agents;

    await page.route('**/api/v1/agents?**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 100));
      await route.fulfill({
        status: 200,
