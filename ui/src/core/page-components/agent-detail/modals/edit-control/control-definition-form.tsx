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

  return (
    <Stack gap="md">
      <Switch
        size="sm"
        color="green.5"
        style={{ width: 'fit-content' }}
        label={
          <LabelWithTooltip
            label="Enabled"
            tooltip="Whether this control is active"
          />
        }
        {...form.getInputProps('enabled', { type: 'checkbox' })}
      />

      <StepNameInput form={form} steps={steps} />

      <MultiSelect
        label={
          <LabelWithTooltip
            label="Stages"
            tooltip="Leave empty to apply to both stages"
          />
        }
        labelProps={labelPropsInline}
        data={[
          { value: 'pre', label: 'Pre (before execution)' },
          { value: 'post', label: 'Post (after execution)' },
        ]}
        size="sm"
        placeholder="All stages"
        clearable
        value={form.values.stages}
        onChange={(value) =>
          form.setFieldValue('stages', value as ControlStage[])
        }
      />

      <Autocomplete
        label={
          <LabelWithTooltip
            label="Selector path"
            tooltip="Path to data. Use * for full step or a root (input, output, name, type, context); subpaths allowed (e.g. input.args.command)."
          />
        }
        labelProps={labelPropsInline}
