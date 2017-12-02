import {
  Autocomplete,
  MultiSelect,
  Select,
  Stack,
  Switch,
  TagsInput,
  TextInput,
} from '@mantine/core';

import type {
  ControlActionDecision,
  ControlExecution,
  ControlStage,
  StepSchema,
} from '@/core/api/types';
import {
  labelPropsInline,
  LabelWithTooltip,
} from '@/core/components/label-with-tooltip';

import { StepNameInput } from './step-name-input';
import type { ControlDefinitionFormProps } from './types';

export type ControlDefinitionFormWithStepsProps = ControlDefinitionFormProps & {
  /** Available steps from the agent */
  steps?: StepSchema[];
  /** Execution environments supported by the selected installed evaluator. */
  supportedExecutions?: readonly ControlExecution[];
};

export const ControlDefinitionForm = ({
  form,
  steps,
  disableSelectorPath = false,
  supportedExecutions,
}: ControlDefinitionFormWithStepsProps) => {
  const executionOptions = [
    { value: 'server' as const, label: 'Server' },
    { value: 'sdk' as const, label: 'SDK' },
  ].filter(
    (option) =>
      !supportedExecutions || supportedExecutions.includes(option.value)
  );

