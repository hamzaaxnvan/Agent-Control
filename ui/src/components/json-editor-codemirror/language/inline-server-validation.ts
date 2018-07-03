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
