import { Stack, TextInput } from '@mantine/core';

import {
  labelPropsInline,
  LabelWithTooltip,
} from '@/core/components/label-with-tooltip';

import type { EvaluatorFormProps } from '../types';
import type { RegexFormValues } from './types';

export const RegexForm = ({ form }: EvaluatorFormProps<RegexFormValues>) => {
  return (
    <Stack gap="md">
      <TextInput
