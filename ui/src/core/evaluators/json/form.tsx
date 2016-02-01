import {
  Checkbox,
  Divider,
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
import type { JsonFormValues } from './types';

export const JsonForm = ({ form }: EvaluatorFormProps<JsonFormValues>) => {
  return (
    <Stack gap="md">
      <Divider label="Schema Validation" labelPosition="left" />

      <Textarea
        label={
          <LabelWithTooltip
            label="JSON Schema"
            tooltip="JSON Schema specification (Draft 7 or later) for structure validation"
          />
        }
        labelProps={labelPropsInline}
        placeholder='{"type": "object", "properties": {...}}'
        minRows={4}
        maxRows={10}
        autosize
        size="sm"
