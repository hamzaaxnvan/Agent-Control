import type { Page } from '@playwright/test';

import { getAgentRoute } from '@/core/constants/agent-routes';

import {
  expect,
  getJsonEditorValue,
  mockData,
  mockRoutes,
  setJsonEditorValue,
  test,
} from './fixtures';

/** Set up mocks for template-backed control flows. */
async function setupTemplateMocks(page: Page) {
  await mockRoutes.agent(page, {
    controls: { data: mockData.controlsWithTemplate },
  });
  await page.route('**/api/v1/controls/10/data', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: mockData.templateControl.control }),
    });
  });
  await mockRoutes.controlRenderTemplate(page);
  await mockRoutes.controlPatch(page);
}

test.describe('Control Templates', () => {
  const agentId = 'customer-support-bot';
  const controlsUrl = getAgentRoute(agentId, { tab: 'controls' });
  const editTemplateUrl = getAgentRoute(agentId, {
    tab: 'controls',
    query: { modal: 'edit', controlId: '10' },
  });
  const editRawUrl = getAgentRoute(agentId, {
    tab: 'controls',
    query: { modal: 'edit', controlId: '1' },
  });

  // ---------------------------------------------------------------------------
  // Template badge in controls list
  // ---------------------------------------------------------------------------

  test.describe('Template badge in controls list', () => {
    test('displays Template badge for template-backed controls', async ({
      mockedPage,
    }) => {
      // Given: an agent with both raw and template-backed controls
      await setupTemplateMocks(mockedPage);

      // When: navigating to the controls list
      await mockedPage.goto(controlsUrl);

      // Then: the template-backed control row shows a "Template" badge
      const badge = mockedPage
        .locator('table')
        .getByText('Template', { exact: true });
      await expect(badge).toBeVisible();
    });

    test('does not display Template badge for raw controls', async ({
      mockedPage,
    }) => {
      // Given: an agent with only raw controls (default mock data)

      // When: navigating to the controls list
      await mockedPage.goto(controlsUrl);

      // Then: no "Template" badge appears anywhere in the table
      const badges = mockedPage
        .locator('table')
        .getByText('Template', { exact: true });
      await expect(badges).toHaveCount(0);
    });
  });

  // ---------------------------------------------------------------------------
  // Template-backed control editing
  // ---------------------------------------------------------------------------

  test.describe('Template-backed control editing', () => {
    test('opens parameter form when editing template-backed control', async ({
      mockedPage,
    }) => {
      // Given: a template-backed control with regex and step_name parameters
      await setupTemplateMocks(mockedPage);

      // When: opening the edit modal for the template-backed control
      await mockedPage.goto(editTemplateUrl);

      // Then: the parameter form renders with fields from the template definition
      const dialog = mockedPage.getByRole('dialog');
      await expect(dialog.getByText('Regex Pattern')).toBeVisible();
      await expect(dialog.getByText('Step Name')).toBeVisible();
