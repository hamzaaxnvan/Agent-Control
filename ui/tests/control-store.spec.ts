import type { Page } from '@playwright/test';

import { getAgentRoute } from '@/core/constants/agent-routes';

import {
  expect,
  mockData,
  mockRoutes,
  setJsonEditorValue,
  test,
} from './fixtures';

const agentUrl = getAgentRoute('agent-1', { tab: 'controls' });
const getAgentControlsUrl = (
  query?: Record<string, string | number | boolean>
) => getAgentRoute('agent-1', { tab: 'controls', query });

async function openControlStoreModal(page: Page) {
  await page.goto(agentUrl);
  await page.getByTestId('add-control-button').first().click();
  const modal = page
    .getByRole('dialog')
    .filter({ hasText: 'Browse existing controls or create a new one' });
  await expect(modal).toBeVisible();
  return modal;
}

async function openAddNewControlModal(page: Page) {
  const controlStoreModal = await openControlStoreModal(page);
  await controlStoreModal.getByTestId('footer-new-control-button').click();
  const modal = page
    .getByRole('dialog')
    .filter({ hasText: 'Select an evaluator to create a new control' });
  await expect(modal).toBeVisible();
  return modal;
}

test.describe('Control Store Modal', () => {
  test('displays modal header and description', async ({ mockedPage }) => {
    const modal = await openControlStoreModal(mockedPage);
    await expect(
      modal.getByRole('heading', { name: 'Control store' })
    ).toBeVisible();
    await expect(
      modal.getByText('Browse existing controls or create a new one')
    ).toBeVisible();
  });

  test('displays controls table with available controls', async ({
    mockedPage,
  }) => {
    const modal = await openControlStoreModal(mockedPage);

    await expect(
      modal.getByRole('columnheader', { name: 'Name' })
    ).toBeVisible();
    await expect(
      modal.getByRole('columnheader', { name: 'Description' })
    ).toBeVisible();
    // Status dot column has no header text, so we skip checking for it
    await expect(
      modal.getByRole('columnheader', { name: 'Used by' })
    ).toBeVisible();

    for (const control of mockData.listControls.controls) {
      await expect(
        modal.getByText(control.name, { exact: true })
      ).toBeVisible();
    }
  });

  test('displays usage attribution in Used by column', async ({
    mockedPage,
  }) => {
    const modal = await openControlStoreModal(mockedPage);

    // Two controls show direct agent-name attribution in fixture data.
    await expect(modal.getByText('customer-support-bot')).toBeVisible();
    await expect(modal.getByText('data-analysis-agent')).toBeVisible();
    // One control has no usage and renders as an em dash
    await expect(modal.getByText('—')).toBeVisible();
    // Agent attribution renders as navigation links with pre-filtered search.
    const customerSupportLink = modal.getByRole('link', {
      name: 'customer-support-bot',
    });
    await expect(customerSupportLink).toHaveCount(1);
    await expect(customerSupportLink).toHaveAttribute(
      'href',
      getAgentRoute('customer-support-bot', {
        tab: 'controls',
        query: { q: 'PII Detection' },
      })
    );
  });

  test('Used by link navigates with control name filter applied', async ({
    mockedPage,
  }) => {
    const modal = await openControlStoreModal(mockedPage);

    const customerSupportLink = modal.getByRole('link', {
      name: 'customer-support-bot',
    });
    await customerSupportLink.click();

    // URL should include the agent, controls tab, and q filter with the control name.
    await expect(mockedPage).toHaveURL(
      getAgentRoute('customer-support-bot', {
        tab: 'controls',
        query: { q: 'PII Detection' },
      })
    );

    // Controls search input should be pre-filled with the control name.
    const searchInput = mockedPage.getByTestId('controls-search-input');
    await expect(searchInput).toHaveValue('PII Detection');
  });

  test('can search for controls', async ({ mockedPage }) => {
    const modal = await openControlStoreModal(mockedPage);
    const searchInput = modal.getByPlaceholder('Search controls...');

    // Fill search and wait for debounced API request (300ms debounce)
    const searchPromise = mockedPage.waitForRequest(
      (req) =>
        req.url().includes('/api/v1/controls') && req.url().includes('name=SQL')
    );
    await searchInput.fill('SQL');
    await searchPromise;

    await expect(
      modal.getByText('SQL Injection Guard', { exact: true })
    ).toBeVisible();
    await expect(
      modal.getByText('PII Detection', { exact: true })
    ).not.toBeVisible();
  });

  test('shows empty state when search has no results', async ({
    mockedPage,
  }) => {
    const modal = await openControlStoreModal(mockedPage);
    const searchInput = modal.getByPlaceholder('Search controls...');

    // Fill search and wait for debounced API request
    const searchPromise = mockedPage.waitForRequest(
      (req) =>
        req.url().includes('/api/v1/controls') &&
        req.url().includes('name=NonexistentControl')
    );
    await searchInput.fill('NonexistentControl');
    await searchPromise;

    await expect(modal.getByText('No controls found')).toBeVisible();
  });

  test('can close modal with X button', async ({ mockedPage }) => {
    const modal = await openControlStoreModal(mockedPage);
    await modal.getByTestId('close-control-store-modal-button').click();
    await expect(
      mockedPage.getByText('Browse existing controls or create a new one')
    ).not.toBeVisible();
  });

  test('Copy button opens create control modal', async ({ mockedPage }) => {
    const modal = await openControlStoreModal(mockedPage);
    const tableRow = modal.locator('tbody tr').first();
    await tableRow.getByTestId('copy-control-button').click();

    await expect(
      mockedPage.getByRole('dialog', { name: 'Create Control' })
    ).toBeVisible();
  });

  test('Copy button pre-fills control name and evaluator config', async ({
    mockedPage,
  }) => {
    const modal = await openControlStoreModal(mockedPage);
    const targetRow = modal.locator('tr', { hasText: 'PII Detection' });
    await targetRow.getByTestId('copy-control-button').click();

    const createControlModal = mockedPage.getByRole('dialog', {
      name: 'Create Control',
    });
    await expect(createControlModal).toBeVisible();

    // Check control name is pre-filled with -copy appended (sanitized)
    const controlNameInput =
      createControlModal.getByPlaceholder('Enter control name');
    await expect(controlNameInput).toHaveValue('PII-Detection-copy');

    // Check evaluator config is pre-filled (PII Detection uses regex with SSN pattern)
    const patternInput = createControlModal.getByPlaceholder(
      'Enter regex pattern (e.g., ^.*$)'
    );
    await expect(patternInput).toHaveValue('\\b\\d{3}-\\d{2}-\\d{4}\\b');
  });

  test('Create Control button opens add-new-control modal', async ({
    mockedPage,
  }) => {
    const modal = await openControlStoreModal(mockedPage);
    await modal.getByTestId('footer-new-control-button').click();

    await expect(
      mockedPage.getByText('Select an evaluator to create a new control')
    ).toBeVisible();
  });
});

test.describe('Add New Control Modal', () => {
  test('displays modal header and description', async ({ mockedPage }) => {
    const modal = await openAddNewControlModal(mockedPage);
    await expect(
      modal.getByRole('heading', { name: 'Create Control' })
    ).toBeVisible();
    await expect(
      modal.getByText('Select an evaluator to create a new control')
    ).toBeVisible();
  });

  test('displays evaluators table with available evaluators', async ({
    mockedPage,
  }) => {
    const modal = await openAddNewControlModal(mockedPage);
    await expect(
      modal.getByRole('columnheader', { name: 'Name' })
    ).toBeVisible();
    await expect(
      modal.getByRole('columnheader', { name: 'Description' })
    ).toBeVisible();

    const evaluators = Object.values(mockData.evaluators);
    for (const evaluator of evaluators) {
      await expect(
        modal.getByText(evaluator.name, { exact: true }).first()
      ).toBeVisible();
    }
  });

  test('does not show DefenseClaw when its evaluator package is unavailable', async ({
    mockedPage,
  }) => {
    const evaluatorsWithoutDefenseClaw = Object.fromEntries(
      Object.entries(mockData.evaluators).filter(
        ([id]) => !id.startsWith('defenseclaw.')
      )
    );
    await mockRoutes.evaluators(mockedPage, {
      data: evaluatorsWithoutDefenseClaw,
    });

    const modal = await openAddNewControlModal(mockedPage);

    await expect(modal.getByText('DefenseClaw Rule Pack')).toHaveCount(0);
    await expect(modal.getByText('DefenseClaw OPA Policy')).toHaveCount(0);
  });

  test('can search for evaluators', async ({ mockedPage }) => {
    const modal = await openAddNewControlModal(mockedPage);
    const searchInput = modal.getByPlaceholder('Search evaluators...');
    await searchInput.fill('Regex');

    await expect(modal.getByRole('cell', { name: 'Regex' })).toBeVisible();
    await expect(modal.getByRole('cell', { name: 'SQL' })).not.toBeVisible();
  });

  test('shows empty state when search has no results', async ({
    mockedPage,
  }) => {
    const modal = await openAddNewControlModal(mockedPage);
    const searchInput = modal.getByPlaceholder('Search evaluators...');
    await searchInput.fill('NonexistentEvaluator');

    await expect(modal.getByText('No evaluators found')).toBeVisible();
  });

  test('Use button opens create control modal', async ({ mockedPage }) => {
    const modal = await openAddNewControlModal(mockedPage);
    const tableRow = modal.locator('tbody tr').first();
    await tableRow.getByRole('button', { name: 'Use' }).click();

    await expect(
      mockedPage.getByRole('dialog', { name: 'Create Control' })
    ).toBeVisible();
  });

  test('displays docs link', async ({ mockedPage }) => {
    const modal = await openAddNewControlModal(mockedPage);
    await expect(
      modal.getByText('Learn here on how to add new type of evaluator.')
    ).toBeVisible();
    await expect(modal.getByText('Docs ↗')).toBeVisible();
  });
});

test.describe('Modal Routing', () => {
  test('opens control store modal via URL query parameter', async ({
    mockedPage,
  }) => {
    await mockedPage.goto(getAgentControlsUrl({ modal: 'control-store' }));

    const modal = mockedPage
      .getByRole('dialog')
      .filter({ hasText: 'Browse existing controls or create a new one' });
    await expect(modal).toBeVisible();

    // URL should contain modal parameter
    await expect(mockedPage).toHaveURL(
      getAgentControlsUrl({ modal: 'control-store' })
    );
  });

  test('opens add-new-control modal via URL query parameters', async ({
    mockedPage,
  }) => {
    await mockedPage.goto(
      getAgentControlsUrl({ modal: 'control-store', submodal: 'add-new' })
    );

    // Both modals should be visible
    const controlStoreModal = mockedPage
      .getByRole('dialog')
      .filter({ hasText: 'Browse existing controls or create a new one' });
    await expect(controlStoreModal).toBeVisible();

    const addNewModal = mockedPage
      .getByRole('dialog')
      .filter({ hasText: 'Select an evaluator to create a new control' });
    await expect(addNewModal).toBeVisible();

    // URL should contain both parameters
    await expect(mockedPage).toHaveURL(
      getAgentControlsUrl({ modal: 'control-store', submodal: 'add-new' })
    );
