import type {
  AgentControlsResponse,
  Control,
  GetAgentResponse,
} from '@/core/api/types';
import { getAgentRoute } from '@/core/constants/agent-routes';

import {
  expect,
  focusJsonEditorAt,
  getJsonEditorValue,
  getJsonEditorSuggestions,
  mockData,
  mockRoutes,
  setJsonEditorValue,
  test,
} from './fixtures';

test.describe('Agent Detail Page', () => {
  const agentId = 'agent-1';
  const getAgentControlsUrl = (
    query?: Record<string, string | number | boolean>
  ) => getAgentRoute(agentId, { tab: 'controls', query });
  const agentUrl = getAgentControlsUrl();
  const agentMonitorUrl = getAgentRoute(agentId, { tab: 'monitor' });

  // Type-safe access to mock agent data
  const agentData: GetAgentResponse = mockData.agent;

  test('displays agent header with name and description', async ({
    mockedPage,
  }) => {
    await mockedPage.goto(agentUrl);

    // Check agent name is displayed
    await expect(
      mockedPage.getByRole('heading', { name: agentData.agent.agent_name })
    ).toBeVisible();

    // Check agent description (using non-null assertion since we know mock data has it)
    await expect(
      mockedPage.getByText(agentData.agent.agent_description!)
    ).toBeVisible();
  });

  test('displays tabs navigation', async ({ mockedPage }) => {
    await mockedPage.goto(agentUrl);

    // Check all tabs are present
    await expect(
      mockedPage.getByRole('tab', { name: /Controls/i })
    ).toBeVisible();
    await expect(
      mockedPage.getByRole('tab', { name: /Monitor/i })
    ).toBeVisible();
  });

  test('controls tab is active by default when no stats data', async ({
    mockedPage,
  }) => {
    // Set up mocks with empty stats to ensure Controls tab is shown
    await mockRoutes.agents(mockedPage);
    await mockRoutes.agent(mockedPage);
    await mockRoutes.stats(mockedPage, { data: mockData.emptyStats });

    await mockedPage.goto(agentUrl);

    // Controls tab should be selected when no stats data exists
    const controlsTab = mockedPage.getByRole('tab', { name: /Controls/i });
    await expect(controlsTab).toHaveAttribute('aria-selected', 'true');

    // Monitor tab should not be selected
    const monitorTab = mockedPage.getByRole('tab', { name: /Monitor/i });
    await expect(monitorTab).toHaveAttribute('aria-selected', 'false');
  });

  test('monitor tab is active by default when stats data exists', async ({
    mockedPage,
  }) => {
    // Set up mocks with stats data to ensure Monitor tab is shown
    await mockRoutes.agents(mockedPage);
    await mockRoutes.agent(mockedPage);
    await mockRoutes.stats(mockedPage, { data: mockData.stats });

    await mockedPage.goto(agentMonitorUrl);

    // Wait for stats to load and tab to be set
    await mockedPage.waitForTimeout(100);

    // Monitor tab should be selected when stats data exists
    const monitorTab = mockedPage.getByRole('tab', { name: /Monitor/i });
    await expect(monitorTab).toHaveAttribute('aria-selected', 'true');

    // Controls tab should not be selected
    const controlsTab = mockedPage.getByRole('tab', { name: /Controls/i });
    await expect(controlsTab).toHaveAttribute('aria-selected', 'false');
  });

  test('displays controls table with data', async ({ mockedPage }) => {
    await mockedPage.goto(agentUrl);

    // Click Controls tab (monitor might be shown by default if stats exist)
    await mockedPage.getByRole('tab', { name: 'Controls' }).click();

    // Wait for controls to load - scope to the Controls tab panel
    const controlsPanel = mockedPage.getByRole('tabpanel', {
      name: /Controls/i,
    });
    await expect(controlsPanel.getByRole('table')).toBeVisible();

    // Check control names are displayed in the controls table
    for (const control of mockData.controls.controls) {
      await expect(controlsPanel.getByText(control.name)).toBeVisible();
    }
  });

  test('filters controls when searching', async ({ mockedPage }) => {
    await mockedPage.goto(agentUrl);

    // Click Controls tab (monitor might be shown by default if stats exist)
    await mockedPage.getByRole('tab', { name: 'Controls' }).click();

    // Wait for controls to load
    const controlsPanel = mockedPage.getByRole('tabpanel', {
      name: /Controls/i,
    });
    await expect(controlsPanel.getByRole('table')).toBeVisible();

    // All controls should be visible initially
    await expect(controlsPanel.getByText('PII Detection')).toBeVisible();
    await expect(controlsPanel.getByText('SQL Injection Guard')).toBeVisible();
    await expect(controlsPanel.getByText('Rate Limiter')).toBeVisible();

    // Type in the search box to filter
    const searchInput = mockedPage.getByPlaceholder('Search controls...');
    await searchInput.fill('SQL');

    // Only the matching control should be visible
    await expect(controlsPanel.getByText('SQL Injection Guard')).toBeVisible();

    // Non-matching controls should be hidden
    await expect(controlsPanel.getByText('PII Detection')).not.toBeVisible();
    await expect(controlsPanel.getByText('Rate Limiter')).not.toBeVisible();

    // Clear search to show all controls again
    await searchInput.clear();
    await expect(controlsPanel.getByText('PII Detection')).toBeVisible();
    await expect(controlsPanel.getByText('SQL Injection Guard')).toBeVisible();
    await expect(controlsPanel.getByText('Rate Limiter')).toBeVisible();
  });

  test('displays control badges for step types and stages', async ({
    mockedPage,
  }) => {
    await mockedPage.goto(agentUrl);

    // Click Controls tab (monitor might be shown by default if stats exist)
    await mockedPage.getByRole('tab', { name: 'Controls' }).click();

    // Wait for controls to load
    const controlsPanel = mockedPage.getByRole('tabpanel', {
      name: /Controls/i,
    });
    await expect(controlsPanel.getByRole('table')).toBeVisible();

    // Check that badges are displayed (LLM or Tool) - scope to controls panel
    await expect(controlsPanel.getByText('LLM').first()).toBeVisible();
    await expect(controlsPanel.getByText('Tool').first()).toBeVisible();

    // Check stage badges (Pre or Post) - scope to controls panel
    await expect(controlsPanel.getByText('Pre').first()).toBeVisible();
    await expect(controlsPanel.getByText('Post').first()).toBeVisible();
  });

  test('shows Add Control button', async ({ mockedPage }) => {
    await mockedPage.goto(agentUrl);

    // Check Add Control button exists
    await expect(
      mockedPage.getByTestId('add-control-button').first()
    ).toBeVisible();
  });

  test('opens control store modal when Add Control is clicked', async ({
    mockedPage,
  }) => {
    await mockedPage.goto(agentUrl);

    // Click Add Control button
    await mockedPage.getByTestId('add-control-button').first().click();

    // Control store modal should be visible
    await expect(
      mockedPage.getByRole('heading', { name: 'Control store' })
    ).toBeVisible();

    // URL should contain modal parameter
    await expect(mockedPage).toHaveURL(
      getAgentControlsUrl({ modal: 'control-store' })
    );
  });

  test('closing edit modal removes query parameters', async ({
    mockedPage,
  }) => {
    // Mock empty stats to ensure controls tab is shown
    await mockRoutes.stats(mockedPage, { data: mockData.emptyStats });

    // Open edit modal via URL
    await mockedPage.goto(
      getAgentRoute(agentId, {
        tab: 'controls',
        query: { modal: 'edit', controlId: '1' },
      })
    );

    const editModal = mockedPage.getByRole('dialog', { name: 'Edit Control' });
    await expect(editModal).toBeVisible();

    // Close the modal via the Cancel button
    await editModal.getByRole('button', { name: 'Cancel' }).click();

    // Modal should be closed
    await expect(editModal).not.toBeVisible();

    // URL should not contain modal parameters
    await expect(mockedPage).not.toHaveURL(/.*\?modal=/);
  });

  test('closes edit modal when control is successfully updated', async ({
    mockedPage,
  }) => {
    // Mock empty stats to ensure controls tab is shown
    await mockRoutes.stats(mockedPage, { data: mockData.emptyStats });

    // Open edit modal via URL
    await mockedPage.goto(
      getAgentRoute(agentId, {
        tab: 'controls',
        query: { modal: 'edit', controlId: '1' },
      })
    );

    const editModal = mockedPage.getByRole('dialog', { name: 'Edit Control' });
    await expect(editModal).toBeVisible();

    // Mock successful API response for control update
    await mockedPage.route(
      '**/api/v1/controls/*/data',
      async (route, request) => {
        if (request.method() === 'PUT') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({}),
          });
        } else {
          await route.continue();
        }
      }
    );

    // Submit the form
    const saveButton = editModal.getByRole('button', { name: /Save/i });
    await saveButton.click();

    // Wait for confirmation modal and confirm
    await mockedPage.waitForTimeout(300); // Wait for modal animation
    const confirmButton = mockedPage.getByRole('button', { name: /Confirm/i });
    await confirmButton.click({ force: true });

    // Wait for modal to close
    await expect(editModal).not.toBeVisible({ timeout: 5000 });

    // URL should not contain any modal parameters
    await expect(mockedPage).not.toHaveURL(/.*\?modal=/);
  });

  test('shows loading state while fetching controls', async ({ page }) => {
    await mockRoutes.config(page);
    let resolveControls: () => void;
    const controlsPromise = new Promise<void>((resolve) => {
      resolveControls = resolve;
    });

    // Mock agent controls - wait for manual trigger
    await page.route('**/api/v1/agents/*/controls', async (route) => {
      await controlsPromise;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.controls),
      });
    });

    // Mock single agent (registered after controls route)
    await page.route('**/api/v1/agents/*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.agent),
      });
    });

    await page.goto(agentUrl);

    // Check for loading indicator (controls request is blocked, so loading state is guaranteed)
    await expect(page.getByText('Loading controls...')).toBeVisible();

    // Release the controls request
    resolveControls!();

    // Wait for controls to load
    await expect(page.getByRole('table')).toBeVisible();
  });

  test('handles agent not found error', async ({ page }) => {
    await mockRoutes.config(page);
    // Mock controls to return 404
    await page.route('**/api/v1/agents/*/controls', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Agent not found' }),
      });
    });

    // Mock agent to return 404
    await page.route('**/api/v1/agents/*', async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Agent not found' }),
      });
    });

