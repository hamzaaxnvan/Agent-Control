import {
  ActionIcon,
  Box,
  Divider,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  TagsInput,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { Button } from '@rungalileo/jupiter-ds';
import { IconTrash } from '@tabler/icons-react';

import type { EvaluatorFormProps } from '../types';
import {
  DEFENSECLAW_SEVERITIES,
  type DefenseClawRuleFormValue,
  type DefenseClawRulePackFormValues,
} from './types';

export const createBlankDefenseClawRule = (): DefenseClawRuleFormValue => ({
  id: '',
