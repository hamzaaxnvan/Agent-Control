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
