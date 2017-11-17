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
        styles={{ input: { fontFamily: 'monospace' } }}
        {...form.getInputProps('json_schema')}
      />

      <Divider label="Field Validation" labelPosition="left" />

      <TextInput
        label={
          <LabelWithTooltip
            label="Required fields"
            tooltip="Comma-separated list of required field paths (supports dot notation)"
          />
        }
        labelProps={labelPropsInline}
        placeholder="field1, nested.field, data.items"
        size="sm"
        {...form.getInputProps('required_fields')}
      />

      <Textarea
        label={
          <LabelWithTooltip
            label="Field types"
            tooltip="JSON mapping of field paths to expected types (string, number, integer, boolean, array, object, null)"
          />
        }
        labelProps={labelPropsInline}
        placeholder='{"name": "string", "age": "integer", "active": "boolean"}'
        minRows={3}
        maxRows={8}
        autosize
        size="sm"
        styles={{ input: { fontFamily: 'monospace' } }}
        {...form.getInputProps('field_types')}
      />
