/**
 * Integration tests for the Luna evaluator form
 */

import { expect, test } from '../fixtures';
import { openEvaluatorForm } from './helpers';

test.describe('Luna Evaluator', () => {
  test('displays scorer fields', async ({ mockedPage }) => {
    await openEvaluatorForm(mockedPage, 'Galileo Luna');

    await expect(
      mockedPage.getByText('Scorer label', { exact: true })
