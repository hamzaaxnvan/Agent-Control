import type { UseFormReturnType } from '@mantine/form';
import type { ReactNode } from 'react';

import type {
  Control,
  ControlActionDecision,
  ControlExecution,
  ControlStage,
  EvaluatorSchema,
  ProblemDetail,
  StepSchema,
} from '@/core/api/types';

// Re-export evaluator form types for convenience
export type { JsonFormValues } from '@/core/evaluators/json/types';
export type { ListFormValues } from '@/core/evaluators/list/types';
export type {
  LunaFormValues,
  LunaOperator,
  LunaPayloadField,
} from '@/core/evaluators/luna/types';
export type { RegexFormValues } from '@/core/evaluators/regex/types';
export type { SqlFormValues } from '@/core/evaluators/sql/types';
