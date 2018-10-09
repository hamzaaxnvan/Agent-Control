import type { EvaluatorDefinition } from '../types';
import { JsonForm } from './form';
import type { JsonFormValues } from './types';

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

/**
 * JSON evaluator definition.
 *
 * Validates JSON structure, types, constraints, and patterns.
 */
