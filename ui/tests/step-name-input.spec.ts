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

    const modal = mockedPage.getByRole('dialog', { name: 'Create Control' });
    await expect(
      modal.getByPlaceholder('No steps registered via SDK')
    ).toBeVisible();

    // Click the visible "Regex" label (switch is in ScrollArea and can be out of viewport)
    await modal.getByText('Regex', { exact: true }).click();

    await expect(modal.getByPlaceholder('^db_.*')).toBeVisible();
    await expect(
      modal.getByPlaceholder('No steps registered via SDK')
    ).not.toBeVisible();
  });

  test('can type in regex field and value persists when toggling', async ({
    mockedPage,
  }) => {
    await openEvaluatorForm(mockedPage, 'Regex');

    const modal = mockedPage.getByRole('dialog', { name: 'Create Control' });
    await modal.getByText('Regex', { exact: true }).click();

    const regexInput = modal.getByPlaceholder('^db_.*');
    await regexInput.fill('^db_.*');

    await expect(regexInput).toHaveValue('^db_.*');

    // Toggle off to names mode
    await modal.getByText('Regex', { exact: true }).click();
    await expect(
