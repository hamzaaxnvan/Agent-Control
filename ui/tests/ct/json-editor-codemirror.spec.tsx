/// <reference path="./playwright-jsx-runtime.d.ts" />
/** @jsxImportSource playwright */

/**
 * Playwright component tests: real browser, Vite bundle, no Next.js server.
 *
 * The pragma uses `playwright/jsx-runtime` (see `playwright` package exports). Root
 * `tsconfig.json` uses `"jsx": "preserve"` for Next.js; without this, `mount()` would
 * serialize raw function components and the CT bundle rejects them.
 */

import { expect, test } from '@playwright/experimental-ct-react';

// One binding per import: CT Babel only strips/replaces imports whose specifiers are
// all JSX tag names; mixing `CT_JSON_EDITOR_TEST_ID` with the host leaves a real
// function reference and mount() fails to serialize the component.
import { JsonEditorCodeMirrorCtHost } from '../../src/components/json-editor-codemirror/json-editor-codemirror.playwright-story';
import { CT_JSON_EDITOR_TEST_ID } from '../../src/components/json-editor-codemirror/json-editor-codemirror.playwright-story';
import {
  focusJsonEditorAt,
  getJsonEditorSuggestions,
  getJsonEditorValue,
  setJsonEditorValue,
} from '../json-editor-bridge';

const EDITOR = CT_JSON_EDITOR_TEST_ID;

test.describe('JsonEditorCodeMirror (component)', () => {
  test('evaluator-config mode loads empty object document', async ({
    mount,
    page,
  }) => {
    await mount(<JsonEditorCodeMirrorCtHost mode="evaluator-config" />);
    await expect(
      page.getByTestId('json-editor-codemirror-ct-host')
    ).toBeVisible();
    const raw = await getJsonEditorValue(page, EDITOR);
    expect(JSON.parse(raw)).toEqual({});
  });

  test('control mode loads minimal valid control document', async ({
    mount,
    page,
  }) => {
    await mount(<JsonEditorCodeMirrorCtHost mode="control" />);
    const raw = await getJsonEditorValue(page, EDITOR);
    const parsed = JSON.parse(raw) as {
      execution: string;
      condition: unknown;
