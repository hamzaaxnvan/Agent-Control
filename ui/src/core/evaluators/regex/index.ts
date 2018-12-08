import type { EvaluatorDefinition } from '../types';
import { RegexForm } from './form';
import type { RegexFormValues } from './types';

/**
 * Regex evaluator definition.
 *
 * Validates content against a regular expression pattern.
 */
export const regexEvaluator: EvaluatorDefinition<RegexFormValues> = {
  id: 'regex',
  displayName: 'Regex',

  initialValues: {
    pattern: '^.*$',
  },

  validate: {
    pattern: (value) => {
      if (!value || (value as string).trim() === '') {
        return 'Pattern is required';
      }
