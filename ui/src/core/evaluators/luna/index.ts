import type { EvaluatorDefinition } from '../types';
import { LunaForm } from './form';
import type { LunaFormValues } from './types';

/** Numeric operators that require a numeric threshold. */
const NUMERIC_OPERATORS = new Set<LunaFormValues['operator']>([
  'gt',
  'gte',
  'lt',
  'lte',
]);

/** Helper to safely parse JSON or return null */
const parseJsonOrNull = (value: string): unknown => {
  if (!value || value.trim() === '') return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
};

/** Helper to stringify JSON or return empty string */
const stringifyOrEmpty = (value: unknown): string => {
  if (value == null) return '';
  return JSON.stringify(value, null, 2);
};

/** Helper to return trimmed string or null */
const stringOrNull = (value: string): string | null =>
  value.trim() === '' ? null : value;

/**
 * Coerce a threshold form value (always a string) into the API representation.
 * Numeric-looking values become numbers; empty becomes null; anything else
 * is passed through as a string (e.g. for `eq`/`contains` on text scores).
 */
const coerceThreshold = (value: string): string | number | null => {
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const num = Number(trimmed);
  return Number.isNaN(num) ? trimmed : num;
};

/**
 * Luna (Galileo) direct scorer evaluator definition.
 *
 * Invokes a Galileo Luna scorer and applies a local threshold comparison to
 * the returned score. One of scorer label, scorer ID, or scorer version ID
 * must be provided.
 */
export const lunaEvaluator: EvaluatorDefinition<LunaFormValues> = {
  id: 'galileo.luna',
  displayName: 'Galileo Luna',

  initialValues: {
    scorer_label: '',
    scorer_id: '',
    scorer_version_id: '',
    threshold: '0.5',
    operator: 'gte',
    payload_field: 'input',
    timeout_ms: 10000,
    scorer_config: '',
  },

  validate: {
    scorer_label: (_value, values) => {
      const v = values as LunaFormValues;
