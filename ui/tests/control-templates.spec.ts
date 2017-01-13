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

      // And: the managed-by-template info is shown
      await expect(dialog.getByText(/managed by the template/)).toBeVisible();
    });

    test('shows Template badge in the editor header', async ({
      mockedPage,
    }) => {
      // Given: a template-backed control
      await setupTemplateMocks(mockedPage);

      // When: opening the edit modal
      await mockedPage.goto(editTemplateUrl);

      // Then: the Template badge is visible in the dialog header
      const dialog = mockedPage.getByRole('dialog');
      await expect(
        dialog.getByText('Template', { exact: true }).first()
      ).toBeVisible();
    });

    test('shows Parameters and Full JSON mode switcher', async ({
      mockedPage,
    }) => {
      // Given: a template-backed control in edit mode
      await setupTemplateMocks(mockedPage);

      // When: opening the edit modal
      await mockedPage.goto(editTemplateUrl);

      // Then: both mode options are visible in the segmented control
      const dialog = mockedPage.getByRole('dialog');
      await expect(
        dialog.getByText('Parameters', { exact: true })
      ).toBeVisible();
      await expect(
        dialog.locator('label').getByText('Full JSON')
      ).toBeVisible();
    });

    test('opens unrendered template controls without rendered fields', async ({
      mockedPage,
    }) => {
      await mockRoutes.agent(mockedPage, {
        controls: { data: mockData.controlsWithUnrenderedTemplate },
      });
      await mockRoutes.controlRenderTemplate(mockedPage);

      await mockedPage.goto(
        getAgentRoute(agentId, {
          tab: 'controls',
          query: { modal: 'edit', controlId: '11' },
        })
      );

      const dialog = mockedPage.getByRole('dialog');
      await expect(dialog.getByText('Template Parameters')).toBeVisible();
      await expect(
        dialog.getByText('This template has no configurable parameters.')
      ).toBeVisible();
      await expect(dialog.getByText('Something went wrong')).not.toBeVisible();
    });

    test('can toggle to Full JSON mode and see template JSON', async ({
      mockedPage,
    }) => {
      // Given: the template edit modal is open in Parameters mode
      await setupTemplateMocks(mockedPage);
      await mockedPage.goto(editTemplateUrl);
      const dialog = mockedPage.getByRole('dialog');

      // When: switching to Full JSON mode
      await dialog.locator('label').getByText('Full JSON').click();

      // Then: the JSON editor shows the full TemplateControlInput with template structure
      const jsonEditor = dialog.getByTestId('template-json-textarea');
      await expect(jsonEditor).toBeVisible();
      const jsonContent = await getJsonEditorValue(
        mockedPage,
        'template-json-textarea'
      );
      expect(jsonContent).toContain('"template"');
      expect(jsonContent).toContain('"template_values"');
      expect(jsonContent).toContain('"definition_template"');
    });

    test('can switch from Full JSON back to Parameters', async ({
      mockedPage,
    }) => {
      // Given: the template edit modal is in Full JSON mode
      await setupTemplateMocks(mockedPage);
      await mockedPage.goto(editTemplateUrl);
      const dialog = mockedPage.getByRole('dialog');
      await dialog.locator('label').getByText('Full JSON').click();
      await expect(dialog.getByTestId('template-json-textarea')).toBeVisible();

