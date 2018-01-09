import {
  Divider,
  NumberInput,
  Select,
  Stack,
  Textarea,
  TextInput,
} from '@mantine/core';

import {
  labelPropsInline,
  LabelWithTooltip,
} from '@/core/components/label-with-tooltip';

import type { EvaluatorFormProps } from '../types';
import type { LunaFormValues } from './types';

export const LunaForm = ({ form }: EvaluatorFormProps<LunaFormValues>) => {
  const thresholdDisabled = form.values.operator === 'any';

  return (
    <Stack gap="md">
      <Divider label="Scorer" labelPosition="left" />

      <TextInput
        label={
          <LabelWithTooltip
            label="Scorer label"
            tooltip="Preset, registered, or fine-tuned Luna scorer label to invoke. Provide a label, scorer ID, or scorer version ID."
          />
        }
        labelProps={labelPropsInline}
        placeholder="toxicity"
        size="sm"
        {...form.getInputProps('scorer_label')}
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Scorer ID"
            tooltip="Optional Galileo scorer identifier to invoke."
          />
        }
        labelProps={labelPropsInline}
        placeholder="Leave empty unless targeting a specific scorer"
        size="sm"
        {...form.getInputProps('scorer_id')}
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Scorer version ID"
            tooltip="Optional Galileo scorer version identifier to invoke."
          />
        }
        labelProps={labelPropsInline}
        placeholder="Leave empty for latest"
        size="sm"
        {...form.getInputProps('scorer_version_id')}
      />

      <Divider label="Comparison" labelPosition="left" />

      <Select
        label={
          <LabelWithTooltip
            label="Operator"
            tooltip="Comparison operator applied to the raw Luna score. Numeric operators require a numeric threshold; 'Any' matches regardless of threshold."
          />
        }
        labelProps={labelPropsInline}
        data={[
          { value: 'gt', label: '> (greater than)' },
          { value: 'gte', label: '>= (greater than or equal)' },
          { value: 'lt', label: '< (less than)' },
          { value: 'lte', label: '<= (less than or equal)' },
          { value: 'eq', label: '= (equal)' },
          { value: 'ne', label: '!= (not equal)' },
          { value: 'contains', label: 'Contains' },
          { value: 'any', label: 'Any' },
        ]}
        size="sm"
        {...form.getInputProps('operator')}
        onChange={(value) =>
          form.setFieldValue(
            'operator',
            (value as LunaFormValues['operator']) || 'gte'
          )
        }
      />

      <TextInput
        label={
          <LabelWithTooltip
            label="Threshold"
            tooltip="Local threshold used to decide whether the control matches. Numeric for numeric operators (e.g., 0.5); not used when operator is 'Any'."
          />
        }
        labelProps={labelPropsInline}
        placeholder="0.5"
        size="sm"
        disabled={thresholdDisabled}
        {...form.getInputProps('threshold')}
      />

      <Divider label="Advanced" labelPosition="left" />

      <Select
