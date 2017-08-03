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
