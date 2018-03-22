/**
 * Integration tests for the List evaluator form
 */

import { expect, test } from '../fixtures';
import { openEvaluatorForm } from './helpers';

test.describe('List Evaluator', () => {
  test('displays all list form fields', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'List');

    // Values textarea (use exact match to avoid matching description)
    await expect(mockedPage.getByText('Values', { exact: true })).toBeVisible();
    await expect(
      mockedPage.getByPlaceholder('Enter values (one per line)')
    ).toBeVisible();

    // Logic select
    await expect(mockedPage.getByText('Logic', { exact: true })).toBeVisible();
