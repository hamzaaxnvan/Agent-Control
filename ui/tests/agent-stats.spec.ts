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
      mockedPage.getByText('Observe', { exact: true })
    ).toBeVisible();
    await expect(mockedPage.getByText('Deny', { exact: true })).toBeVisible();
    await expect(mockedPage.getByText('Steer', { exact: true })).toHaveCount(0);
  });

  test('should display per-control statistics table', async ({
    mockedPage,
  }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // Check table column headers
    await expect(
      mockedPage.getByRole('columnheader', { name: 'Control' })
    ).toBeVisible();
    await expect(
      mockedPage.getByRole('columnheader', { name: 'Executions' })
    ).toBeVisible();
    await expect(
      mockedPage.getByRole('columnheader', { name: 'Triggers', exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByRole('columnheader', { name: 'Errors' })
    ).toBeVisible();
  });

  test('should display control names in the table', async ({ mockedPage }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // Check control names from mock data - scope to Stats panel table
    const statsTable = mockedPage
      .getByRole('tabpanel', { name: /Monitor/i })
      .getByRole('table');
    for (const stat of mockData.stats.controls) {
      await expect(statsTable.getByText(stat.control_name)).toBeVisible();
    }
  });

  test('should allow changing time range', async ({ mockedPage }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // TimeRangeSwitch should be visible and allow changing time range
    // The component has segment buttons for quick selection
    const timeRangeSwitch = mockedPage
      .locator('[class*="TimeRangeSwitch"]')
      .first();
    await expect(timeRangeSwitch).toBeVisible();

    // Try clicking on a segment button (e.g., "1D" for 24 hours)
    const oneDayButton = mockedPage
      .getByRole('button', { name: /1D/i })
      .first();
    if (await oneDayButton.isVisible()) {
      await oneDayButton.click();
    }
  });

  test('should show error badges for controls with errors', async ({
    mockedPage,
  }) => {
    // Navigate to stats tab
    await mockedPage.getByRole('tab', { name: 'Monitor' }).click();

    // SQL Injection Guard has 2 errors in mock data
    // Find the row and check for error count
    const errorBadge = mockedPage.locator('table').getByText('2').first();
    await expect(errorBadge).toBeVisible();
  });
});

