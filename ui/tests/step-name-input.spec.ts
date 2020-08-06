/**
 * Integration tests for the StepNameInput component (step name / regex mode toggle).
 * The component is exercised within the Create Control modal.
 */

import { openEvaluatorForm } from './evaluators/helpers';
import { expect, mockData, mockRoutes, test } from './fixtures';

test.describe('Step Name Input', () => {
  test('displays Step name label and Regex toggle', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'Regex');

    const modal = mockedPage.getByRole('dialog', { name: 'Create Control' });
    await expect(modal.getByText('Step name')).toBeVisible();
    await expect(modal.getByText('Regex')).toBeVisible();
  });

  test('defaults to names mode with step selector', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'Regex');

    const modal = mockedPage.getByRole('dialog', { name: 'Create Control' });
    const namesInput = modal.getByPlaceholder('No steps registered via SDK');
    await expect(namesInput).toBeVisible();
    await expect(modal.getByPlaceholder('^db_.*')).not.toBeVisible();
  });

  test('toggling Regex on shows regex input and hides names input', async ({
    mockedPage,
  }) => {
    await openEvaluatorForm(mockedPage, 'Regex');
