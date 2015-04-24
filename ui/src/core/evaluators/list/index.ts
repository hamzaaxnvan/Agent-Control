import type { EvaluatorDefinition } from '../types';
import { ListForm } from './form';
import type { ListFormValues } from './types';

/**
 * List evaluator definition.
 *
 * Validates content against a list of values with configurable matching logic.
 */
export const listEvaluator: EvaluatorDefinition<ListFormValues> = {
  id: 'list',
