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
