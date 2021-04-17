import { ActionIcon, Box, Group, Text, Tooltip } from '@mantine/core';
import { useClipboard, useDebouncedValue } from '@mantine/hooks';
import {
  IconClipboardCheck,
  IconClipboardCopy,
  IconCode,
} from '@tabler/icons-react';
import { findNodeAtLocation, parseTree } from 'jsonc-parser';
import dynamic from 'next/dynamic';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  extractEvaluatorNames,
  findEvaluatorConfigEdit,
  findSteeringContextEdit,
  fixJsonCommas,
  getEmptyValueHints,
  getJsonEditorCompletionItems,
  setupJsonEditorLanguageSupport,
  TEMPLATE_DEFINITION_PREFIX,
} from '@/components/json-editor-monaco/json-editor-monaco-language';
import { isApiError } from '@/core/api/errors';
import { LabelWithTooltip } from '@/core/components/label-with-tooltip';

import { ApiErrorAlert } from './api-error-alert';
import type { JsonEditorViewProps } from './types';

const MonacoEditor = dynamic(
  async () => (await import('@monaco-editor/react')).default,
  { ssr: false }
);

type MonacoModule = typeof import('monaco-editor');
type MonacoEditorInstance =
  import('monaco-editor').editor.IStandaloneCodeEditor;

type JsonEditorTestElement = HTMLDivElement & {
  __getJsonEditorValue?: () => string;
  __getJsonEditorLanguageId?: () => string | null;
  __setJsonEditorValue?: (value: string) => void;
  __isJsonEditorReady?: () => boolean;
  __focusJsonEditorAt?: (lineNumber: number, column: number) => void;
  __triggerJsonEditorSuggest?: () => void;
  __getJsonEditorSuggestions?: (
    lineNumber: number,
    column: number
  ) => Array<{ label: string; detail?: string }>;
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_HEIGHT = 400;
const DEFAULT_VALIDATE_DEBOUNCE_MS = 500;
const DEFAULT_LABEL = 'Configuration (JSON)';
const DEFAULT_TOOLTIP = 'Raw JSON configuration';
const DEFAULT_TEST_ID = 'raw-json-textarea';
const DEFAULT_EDITOR_MODE = 'evaluator-config';
const HINT_DEBOUNCE_MS = 300;
const COMMA_FIX_DEBOUNCE_MS = 800;
const CURSOR_TRIGGER_DEBOUNCE_MS = 50;
const HINT_CSS_CLASS = 'json-editor-value-hint';
const VALIDATION_ERROR_CSS_CLASS = 'json-editor-validation-error';

// Inject validation error highlighting styles once.
if (typeof document !== 'undefined') {
  const id = 'json-editor-validation-error-styles';
  if (!document.getElementById(id)) {
    const style = document.createElement('style');
    style.id = id;
    style.textContent = `.${VALIDATION_ERROR_CSS_CLASS} { background-color: rgba(255, 0, 0, 0.15); border-bottom: 2px wavy rgba(255, 0, 0, 0.6); }`;
    document.head.appendChild(style);
  }
}

// Dynamic hint styles — each unique hint text gets a CSS class with ::after content.
// Monaco 0.55 doesn't support `after.content` in decorations, so we use
// `afterContentClassName` with CSS `::after` pseudo-elements instead.
let hintStyleEl: HTMLStyleElement | null = null;
let hintClassCounter = 0;
const hintClassMap = new Map<string, string>();

function getHintClassName(hintText: string): string {
  let cls = hintClassMap.get(hintText);
  if (cls) return cls;

  cls = `${HINT_CSS_CLASS}-${hintClassCounter++}`;
  hintClassMap.set(hintText, cls);

  if (typeof document !== 'undefined') {
    if (!hintStyleEl) {
      hintStyleEl = document.createElement('style');
      hintStyleEl.id = 'json-editor-hint-styles';
      document.head.appendChild(hintStyleEl);
    }
    const escaped = hintText.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    hintStyleEl.textContent += `.${cls}::after { content: "${escaped}"; color: var(--mantine-color-gray-5); font-style: italic; pointer-events: none; }\n`;
  }
  return cls;
}

const EDITOR_OPTIONS: import('monaco-editor').editor.IStandaloneEditorConstructionOptions =
  {
    automaticLayout: true,
    quickSuggestions: false,
    suggestOnTriggerCharacters: true,
    wordBasedSuggestions: 'off',
    suggest: {
      showWords: false,
      preview: true,
      showIcons: true,
      insertMode: 'replace',
    },
    snippetSuggestions: 'inline',
    acceptSuggestionOnEnter: 'off',
    fontFamily:
      'ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, monospace',
    fontSize: 12,
    formatOnPaste: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    tabSize: 2,
    insertSpaces: true,
    wordWrap: 'off',
    bracketPairColorization: { enabled: true },
    guides: { bracketPairs: true, indentation: true },
    stickyScroll: { enabled: true },
    padding: { top: 8, bottom: 8 },
    folding: true,
    showFoldingControls: 'mouseover',
    renderLineHighlight: 'line',
    cursorSmoothCaretAnimation: 'on',
    smoothScrolling: true,
  };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isSuggestWidgetVisible(editor: MonacoEditorInstance): boolean {
  return (
    editor
      .getDomNode()
      ?.querySelector('.suggest-widget')
      ?.classList.contains('visible') ?? false
  );
}

function replaceAllContent(
  editor: MonacoEditorInstance,
  newText: string,
  source: string
) {
  const model = editor.getModel();
  if (!model) return;
  editor.executeEdits(source, [
    { range: model.getFullModelRange(), text: newText },
  ]);
  const pos = editor.getPosition();
  if (pos && pos.lineNumber > model.getLineCount()) {
    editor.setPosition({ lineNumber: model.getLineCount(), column: 1 });
  }
}

function tryFormat(text: string): string | null {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return null;
  }
}

/** Check if the cursor is at a position where auto-triggering suggestions is useful. */
function shouldAutoTriggerSuggest(
  line: string | undefined,
  column: number,
  skipStringTrigger: boolean,
  hasSuggestions: () => boolean
): boolean {
  if (!line) return false;
  const beforeCursor = line.substring(0, column - 1);
  const afterCursor = line.substring(column - 1);

  // Blank / comma-only line — always trigger (even after Enter)
  if (/^\s*,?\s*$/.test(line)) return true;

  // Typing `"` at a property-key position (whitespace + optional comma + `"`)
  // should trigger property name suggestions immediately.
  if (/^\s*,?\s*"$/.test(beforeCursor) && !afterCursor.includes(':')) {
    return true;
  }

  // Don't trigger string suggestions after typing
  if (skipStringTrigger) return false;

  // Check if inside a string value (not a property key)
  const quotesBefore = beforeCursor.split('"').length - 1;
  const isInString = quotesBefore % 2 === 1 && /^[^"]*"/.test(afterCursor);
  if (!isInString) return false;
  if (/^\s*:/.test(afterCursor.replace(/^[^"]*"/, ''))) return false;

  const openIdx = beforeCursor.lastIndexOf('"');
  const closeIdx = afterCursor.indexOf('"');
  const contentLen =
    openIdx >= 0 && closeIdx >= 0
      ? beforeCursor.length - openIdx - 1 + closeIdx
      : 999;
