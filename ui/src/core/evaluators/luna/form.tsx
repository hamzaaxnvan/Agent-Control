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
