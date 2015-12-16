import { expect, type Page } from '@playwright/test';

export async function getJsonEditorValue(
  page: Page,
  testId: string
): Promise<string> {
  const locator = page.getByTestId(testId);
  await expect(locator).toBeVisible();
  await page.waitForFunction((selector) => {
    const element = document.querySelector(`[data-testid="${selector}"]`) as {
      __getJsonEditorValue?: () => string;
      __isJsonEditorReady?: () => boolean;
    } | null;

    return (
      typeof element?.__getJsonEditorValue === 'function' &&
      element.__isJsonEditorReady?.() === true
    );
  }, testId);

  return locator.evaluate((element) => {
    const target = element as { __getJsonEditorValue?: () => string };
    return target.__getJsonEditorValue?.() ?? '';
  });
}

export async function setJsonEditorValue(
  page: Page,
  testId: string,
  value: string
) {
  const locator = page.getByTestId(testId);
  await expect(locator).toBeVisible();
  await page.waitForFunction((selector) => {
    const element = document.querySelector(`[data-testid="${selector}"]`) as {
      __setJsonEditorValue?: (nextValue: string) => void;
      __isJsonEditorReady?: () => boolean;
    } | null;

    return (
      typeof element?.__setJsonEditorValue === 'function' &&
      element.__isJsonEditorReady?.() === true
    );
  }, testId);

  await locator.evaluate((element, nextValue) => {
    const target = element as {
      __setJsonEditorValue?: (v: string) => void;
    };

    if (!target.__setJsonEditorValue) {
      throw new Error('JSON editor bridge not available');
    }

    target.__setJsonEditorValue(nextValue);
