import { getAgentRoute } from '@/core/constants/agent-routes';

import { expect, mockData, mockRoutes, test } from './fixtures';

test.describe('Agent Monitor Tab', () => {
  test.beforeEach(async ({ mockedPage }) => {
    // Navigate to agent detail page
    await mockedPage.goto(getAgentRoute('agent-1', { tab: 'monitor' }));
    // Wait for the page to load
    await expect(
      mockedPage.getByRole('heading', { name: 'customer-support-bot' })
    ).toBeVisible();
  });

  test('should display stats tab and navigate to it', async ({
    mockedPage,
  }) => {
    // Stats tab should be visible
    const statsTab = mockedPage.getByRole('tab', { name: 'Monitor' });
    await expect(statsTab).toBeVisible();

    // Click on stats tab
    await statsTab.click();

    // Should show the stats content - check for summary card metrics (use first() to get summary card, not table header)
    await expect(mockedPage.getByText('Executions').first()).toBeVisible();
    await expect(mockedPage.getByText('Triggers').first()).toBeVisible();
    await expect(mockedPage.getByText('Errors').first()).toBeVisible();
  });

  test('should display time range selector with default value', async ({
    mockedPage,
  }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // Time range selector should be visible (TimeRangeSwitch component)
    // Look for the component by finding the segment buttons or menu button
    const timeRangeSwitch = mockedPage
      .locator('[class*="TimeRangeSwitch"]')
      .first();
    await expect(timeRangeSwitch).toBeVisible();
  });

  test('should display summary statistics', async ({ mockedPage }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // Check total executions
    await expect(
      mockedPage.getByText(
        mockData.stats.totals.execution_count.toLocaleString()
      )
    ).toBeVisible();

    // Check for summary card labels (use first() to get summary card, not table header)
    await expect(mockedPage.getByText('Executions').first()).toBeVisible();
    await expect(mockedPage.getByText('Triggers').first()).toBeVisible();
    await expect(mockedPage.getByText('Errors').first()).toBeVisible();
  });

  test('should display actions distribution section', async ({
    mockedPage,
  }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // Check actions distribution header
    await expect(mockedPage.getByText('Actions Distribution')).toBeVisible();

    // Check action types are displayed (use exact match to avoid matching badges)
    await expect(
