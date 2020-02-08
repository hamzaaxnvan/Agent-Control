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
