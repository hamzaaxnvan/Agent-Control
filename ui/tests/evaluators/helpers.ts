/**
 * Shared helpers for evaluator tests
 */

import { getAgentRoute } from '@/core/constants/agent-routes';
import { expect, type Page } from '@playwright/test';

const AGENT_URL = getAgentRoute('agent-1', { tab: 'controls' });

/**
 * Opens the control store and selects an evaluator to create a new control
 */
export async function openEvaluatorForm(page: Page, evaluatorName: string) {
  await page.goto(AGENT_URL);

  // Open control store modal
  await page.getByTestId('add-control-button').first().click();
  const controlStoreModal = page
    .getByRole('dialog')
    .filter({ hasText: 'Browse existing controls or create a new one' });
  await expect(controlStoreModal).toBeVisible();

  // Open the add-new-control modal via footer CTA
  await controlStoreModal.getByTestId('footer-new-control-button').click();
  const addNewModal = page
