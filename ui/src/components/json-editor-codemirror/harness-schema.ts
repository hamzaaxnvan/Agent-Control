import type { JsonSchema } from '@/core/page-components/agent-detail/modals/edit-control/types';

/**
 * Control JSON Schema used by the Playwright harness for JsonEditorCodeMirror.
 * Aligned with mock control schema in ui/tests/fixtures.ts.
 */
export const HARNESS_CONTROL_SCHEMA: JsonSchema = {
  $defs: {
    ControlSelector: {
      type: 'object',
      properties: {
        path: {
          anyOf: [{ type: 'string' }, { type: 'null' }],
          default: '*',
          examples: ['output', 'context.user_id', '*'],
        },
      },
    },
    EvaluatorSpec: {
      type: 'object',
      required: ['name', 'config'],
      properties: {
        name: {
          type: 'string',
          examples: ['regex', 'list'],
