/**
 * Integration tests for the JSON evaluator form
 */

import { expect, test } from '../fixtures';
import { openEvaluatorForm } from './helpers';

test.describe('JSON Evaluator', () => {
  test('displays schema validation section', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'JSON');

    // Use exact match for all labels to avoid matching description or helper text
    await expect(
      mockedPage.getByText('Schema Validation', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByText('JSON Schema', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByPlaceholder('{"type": "object", "properties": {...}}')
    ).toBeVisible();
  });

  test('displays field validation section', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'JSON');

    await expect(
      mockedPage.getByText('Field Validation', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByText('Required fields', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByText('Field types', { exact: true })
