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

export type ConfigViewMode = 'form' | 'json';
export type ControlEditorMode = 'form' | 'json';
export type JsonEditorMode = 'control' | 'evaluator-config' | 'template';

export type JsonSchema = Record<string, unknown>;

export type JsonEditorEvaluatorOption = {
  id: string;
  label: string;
  description?: string | null;
  source: 'global' | 'agent';
  configSchema?: EvaluatorSchema['config_schema'] | null;
};

// Form values type for control definition
// Uses snake_case to match API field names directly
export type ControlDefinitionFormValues = {
  name: string;
  description?: string;
  enabled: boolean;
  step_types: string[];
  stages: ControlStage[];
  step_names: string;
