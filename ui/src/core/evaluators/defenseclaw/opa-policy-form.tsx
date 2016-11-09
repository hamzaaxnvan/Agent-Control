import { Divider, Select, Stack } from '@mantine/core';

import type { EvaluatorFormProps } from '../types';
import {
  DEFENSECLAW_SEVERITIES,
  type DefenseClawOpaPolicyFormValues,
} from './types';

const severityOptions = DEFENSECLAW_SEVERITIES.map((severity) => ({
  value: severity,
  label: severity,
}));

export const DefenseClawOpaPolicyForm = ({
  form,
}: EvaluatorFormProps<DefenseClawOpaPolicyFormValues>) => (
  <Stack gap="md">
    <Divider label="Policy" labelPosition="left" />
    <Select
