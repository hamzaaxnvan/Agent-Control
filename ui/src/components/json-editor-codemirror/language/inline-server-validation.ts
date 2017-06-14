import {
  type Extension,
  type Range,
  StateEffect,
  StateField,
} from '@codemirror/state';
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from '@codemirror/view';
import {
  findNodeAtLocation,
  type Node as JsonNode,
  parseTree,
} from 'jsonc-parser';

import type { ValidationErrorItem } from '@/core/api/types';

type InlineServerValidationPayload = {
  errors: ValidationErrorItem[];
};

export const setInlineServerValidationErrorsEffect =
  StateEffect.define<InlineServerValidationPayload>();

const inlineServerValidationField =
  StateField.define<InlineServerValidationPayload>({
    create: () => ({ errors: [] }),
    update(value, tr) {
      for (const effect of tr.effects) {
        if (effect.is(setInlineServerValidationErrorsEffect)) {
          return effect.value;
        }
      }
      return value;
    },
  });

const INLINE_VALIDATION_ERROR_THEME = EditorView.theme({
  '& .cm-inline-validation-error-key': {
    backgroundColor: 'rgba(255, 0, 0, 0.18)',
    borderBottom: '1px solid rgba(255, 0, 0, 0.55)',
  },
});

class InlineErrorWidget extends WidgetType {
  constructor(private readonly message: string) {
    super();
  }

  toDOM(): HTMLElement {
    const span = document.createElement('span');
    span.textContent = this.message;
    span.style.color = 'var(--mantine-color-red-6)';
    span.style.fontSize = '11px';
    span.style.marginLeft = '8px';
    span.style.padding = '2px 6px';
    span.style.borderRadius = '999px';
    span.style.background = 'rgba(255, 0, 0, 0.12)';
    span.style.whiteSpace = 'nowrap';
    span.style.pointerEvents = 'none';
    return span;
  }
}

type JsonPath = Array<string | number>;

function apiFieldToJsonPath(apiField: string): JsonPath | null {
  let field = apiField.trim();
  if (!field) return null;

  // Backend uses e.g. "data.action.decision".
  const dataPrefix = 'data.';
  if (field.startsWith(dataPrefix)) {
    field = field.slice(dataPrefix.length);
  }

  // Convert simple "foo[0]" patterns into path segments.
  const out: JsonPath = [];
  for (const segment of field.split('.')) {
    if (!segment) continue;
    const m = segment.match(/^([^\[]+)\[(\d+)\]$/);
    if (m) {
      out.push(m[1]);
      out.push(Number(m[2]));
      continue;
    }
    out.push(segment);
  }
  return out;
}

function findKeyAndValueRangesForJsonPath(
  tree: JsonNode | undefined,
  path: JsonPath
): {
  keyRange: { from: number; to: number } | null;
  valueRange: { from: number; to: number } | null;
} {
  if (!tree || path.length === 0) {
    return { keyRange: null, valueRange: null };
  }

  const valueNode = findNodeAtLocation(tree, path);
  const valueRange = valueNode
    ? { from: valueNode.offset, to: valueNode.offset + valueNode.length }
    : null;

  const keySegment = path[path.length - 1];
  let keyRange: { from: number; to: number } | null = null;

  // If the last segment is a string, try to locate the property key token.
  if (typeof keySegment === 'string') {
    const parentPath = path.slice(0, -1);
    const parentNode =
      parentPath.length > 0 ? findNodeAtLocation(tree, parentPath) : tree;

