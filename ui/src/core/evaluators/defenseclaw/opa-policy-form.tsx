import { Divider, Select, Stack } from '@mantine/core';

import type { EvaluatorFormProps } from '../types';
import {
  DEFENSECLAW_SEVERITIES,
  type DefenseClawOpaPolicyFormValues,
} from './types';

const severityOptions = DEFENSECLAW_SEVERITIES.map((severity) => ({
