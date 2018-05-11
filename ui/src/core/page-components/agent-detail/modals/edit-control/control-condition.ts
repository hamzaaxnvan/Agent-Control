import type { ControlDefinition } from '@/core/api/types';
import type { AnyEvaluatorDefinition } from '@/core/evaluators';
import { getEvaluator } from '@/core/evaluators';

export type LeafConditionDetails = {
  selectorPath: string;
  evaluatorName: string;
  evaluatorConfig: Record<string, unknown>;
};

export type ControlConditionState = {
  leafCondition: LeafConditionDetails | null;
  evaluatorId: string;
  evaluator: AnyEvaluatorDefinition | undefined;
  canEditLeafCondition: boolean;
};

function getLeafConditionDetails(
  definition: ControlDefinition
): LeafConditionDetails | null {
  const condition = definition.condition;
  if (!condition.selector || !condition.evaluator) {
    return null;
  }

  return {
