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
  pattern: '',
  title: '',
  severity: 'HIGH',
  confidence: 0.99,
  tags: [],
});

const severityOptions = DEFENSECLAW_SEVERITIES.map((severity) => ({
  value: severity,
  label: severity,
}));

export const DefenseClawRulePackForm = ({
  form,
}: EvaluatorFormProps<DefenseClawRulePackFormValues>) => (
  <Stack gap="md">
    <Divider label="Rules" labelPosition="left" />

    {form.values.rules.map((rule, index) => (
      <Paper key={index} withBorder p="md" radius="sm">
        <Stack gap="sm">
          <Group justify="space-between">
            <Text fw={600} size="sm">
              Rule {index + 1}
            </Text>
            <ActionIcon
              aria-label={`Remove rule ${index + 1}`}
              data-testid={`defenseclaw-remove-rule-${index}`}
              type="button"
              color="red"
              variant="subtle"
              disabled={form.values.rules.length === 1}
              onClick={() => form.removeListItem('rules', index)}
            >
              <IconTrash size={16} />
            </ActionIcon>
          </Group>

          <TextInput
            label="Rule ID"
            placeholder="AC-CMD-RM-RF"
            required
            {...form.getInputProps(`rules.${index}.id`)}
          />
          <TextInput
            label="Title"
            placeholder="Recursive deletion"
            required
            {...form.getInputProps(`rules.${index}.title`)}
          />
          <Textarea
            label="Pattern"
            placeholder="Enter the DefenseClaw pattern"
