import { Checkbox, Select, Stack, Textarea } from '@mantine/core';

import {
  labelPropsInline,
  LabelWithTooltip,
} from '@/core/components/label-with-tooltip';

import type { EvaluatorFormProps } from '../types';
import type { ListFormValues } from './types';

export const ListForm = ({ form }: EvaluatorFormProps<ListFormValues>) => {
  return (
    <Stack gap="md">
      <Textarea
        label={
          <LabelWithTooltip
            label="Values"
            tooltip="List of values to match against (one per line)"
          />
        }
        labelProps={labelPropsInline}
