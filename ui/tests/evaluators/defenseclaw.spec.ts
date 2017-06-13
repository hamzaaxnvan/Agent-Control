/** Integration tests for the DefenseClaw evaluator forms. */

import { expect, test } from '../fixtures';
import { openEvaluatorForm } from './helpers';

test.describe('DefenseClaw Rule Pack Evaluator', () => {
  test('shows typed rule fields and hides wire constants', async ({
    mockedPage,
  }) => {
    await openEvaluatorForm(mockedPage, 'DefenseClaw Rule Pack');

    await expect(
      mockedPage.getByRole('textbox', { name: 'Execution environment' })
    ).toHaveValue('SDK');
    await expect(
      mockedPage.getByRole('textbox', { name: 'Execution environment' })
