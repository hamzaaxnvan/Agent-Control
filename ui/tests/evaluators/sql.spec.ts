/**
 * Integration tests for the SQL evaluator form
 */

import { expect, test } from '../fixtures';
import { openEvaluatorForm } from './helpers';

test.describe('SQL Evaluator', () => {
  test('displays SQL dialect selector', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'SQL');

    await expect(
      mockedPage.getByText('SQL dialect', { exact: true })
    ).toBeVisible();
  });

  test('displays multi-statement controls', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'SQL');

    await expect(
      mockedPage.getByText('Multi-Statement Controls', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByText('Allow multiple statements')
    ).toBeVisible();
    await expect(
      mockedPage.getByText('Max statements', { exact: true })
    ).toBeVisible();
  });

  test('displays operation controls', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'SQL');

    await expect(
      mockedPage.getByText('Operation Controls', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByText('Blocked operations', { exact: true })
    ).toBeVisible();
    await expect(
      mockedPage.getByText('Allowed operations', { exact: true })
    ).toBeVisible();
    await expect(mockedPage.getByText('Block DDL statements')).toBeVisible();
    await expect(mockedPage.getByText('Block DCL statements')).toBeVisible();
  });

  test('displays table/schema access controls', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'SQL');

    await expect(
