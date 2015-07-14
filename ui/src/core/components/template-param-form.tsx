import {
  Select,
  Stack,
  Switch,
  TagsInput,
  Text,
  TextInput,
} from '@mantine/core';
import { useMemo } from 'react';

import type {
  TemplateDefinition,
  TemplateParameterDefinition,
  TemplateValue,
} from '@/core/api/types';

import { labelPropsInline, LabelWithTooltip } from './label-with-tooltip';

type TemplateParamFormProps = {
  template: TemplateDefinition;
  values: Record<string, TemplateValue>;
  onChange: (values: Record<string, TemplateValue>) => void;
  errors?: Record<string, string>;
};

function paramLabel(
  name: string,
  param: TemplateParameterDefinition
): React.ReactNode {
  if (param.description) {
    return <LabelWithTooltip label={param.label} tooltip={param.description} />;
  }
  return param.label;
}

function ParameterInput({
  name,
  param,
  value,
  error,
  onChangeValue,
}: {
  name: string;
  param: TemplateParameterDefinition;
  value: TemplateValue | undefined;
  error?: string;
  onChangeValue: (name: string, value: TemplateValue) => void;
}) {
  const label = paramLabel(name, param);
  const isRequired = param.required !== false;

  switch (param.type) {
    case 'string':
      return (
        <TextInput
          label={label}
          labelProps={param.description ? labelPropsInline : undefined}
          placeholder={param.placeholder ?? undefined}
          required={isRequired}
          value={(value as string) ?? ''}
          onChange={(e) => onChangeValue(name, e.currentTarget.value)}
          error={error}
          size="sm"
        />
      );

    case 'string_list':
      return (
        <TagsInput
          label={label}
          labelProps={param.description ? labelPropsInline : undefined}
          placeholder={
            param.placeholder ? param.placeholder.join(', ') : 'Add items...'
          }
          required={isRequired}
          value={Array.isArray(value) ? (value as string[]) : []}
          onChange={(val) => onChangeValue(name, val)}
          error={error}
          size="sm"
        />
      );

    case 'enum':
      return (
        <Select
          label={label}
