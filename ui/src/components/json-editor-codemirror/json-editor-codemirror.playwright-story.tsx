import { Box, Button, Group } from '@mantine/core';
import { useCallback, useEffect, useState } from 'react';

import type {
  JsonEditorEvaluatorOption,
  JsonEditorMode,
} from '@/core/page-components/agent-detail/modals/edit-control/types';

import { HARNESS_CONTROL_SCHEMA } from './harness-schema';
import { JsonEditorCodeMirror } from './json-editor-codemirror';

/** `data-testid` on the editor root for `tests/json-editor-bridge.ts` helpers. */
export const CT_JSON_EDITOR_TEST_ID = 'codemirror-json-editor-ct';

const DEFAULT_CONTROL_JSON =
  '{"execution":"server","condition":{},"action":{"decision":"allow"}}';

const CT_EVALUATORS: JsonEditorEvaluatorOption[] = [
  {
    id: 'regex',
    label: 'Regex',
    source: 'global',
    configSchema: {
      type: 'object',
      properties: {
        pattern: { type: 'string', default: '.*' },
      },
      required: ['pattern'],
    },
  },
  {
    id: 'json',
    label: 'JSON',
    source: 'global',
    configSchema: {
