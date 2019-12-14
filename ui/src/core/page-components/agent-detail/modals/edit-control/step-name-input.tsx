import {
  Box,
  Group,
  MultiSelect,
  Stack,
  Switch,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import {
  IconAlertCircle,
  IconCircleCheck,
  IconCircleX,
  IconInfoCircle,
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';

import type { StepSchema } from '@/core/api/types';

import type { ControlDefinitionFormProps } from './types';

export type StepNameInputProps = ControlDefinitionFormProps & {
  /** Available steps from the agent */
  steps?: StepSchema[];
};

export function StepNameInput({ form, steps = [] }: StepNameInputProps) {
  const isRegexMode = form.values.step_name_mode === 'regex';
  const [searchValue, setSearchValue] = useState('');

  const handleRegexToggle = (enabled: boolean) => {
    form.setFieldValue('step_name_mode', enabled ? 'regex' : 'names');
  };

  // Convert comma-separated string to array for MultiSelect
  const selectedStepNames = useMemo(() => {
    if (isRegexMode || !form.values.step_names) return [];
    return form.values.step_names
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  }, [form.values.step_names, isRegexMode]);

  // Step options for dropdown - ensure steps is always an array
  const stepOptions = useMemo(() => {
    if (!steps || !Array.isArray(steps)) return [];
    return steps.map((step) => ({
      value: step.name,
      label: step.name,
    }));
  }, [steps]);

  const handleStepNamesChange = (values: string[]) => {
    // Empty means "all steps" on the server
    if (values.length === 0) {
      form.setFieldValue('step_names', '');
      return;
    }

    form.setFieldValue('step_names', values.join(', '));
  };

