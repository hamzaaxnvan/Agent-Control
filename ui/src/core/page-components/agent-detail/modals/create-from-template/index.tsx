import {
  Alert,
  Box,
  Divider,
  Group,
  Paper,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { Button } from '@rungalileo/jupiter-ds';
import { IconArrowLeft, IconX } from '@tabler/icons-react';
import { useCallback, useState } from 'react';

import { isApiError } from '@/core/api/errors';
import type {
  ProblemDetail,
  TemplateControlInput,
  TemplateDefinition,
  TemplateValue,
} from '@/core/api/types';
import { TemplateParamForm } from '@/core/components/template-param-form';
import { TemplatePreview } from '@/core/components/template-preview';
import { useAddControlToAgent } from '@/core/hooks/query-hooks/use-add-control-to-agent';
import { openActionConfirmModal } from '@/core/utils/modals';

import { sanitizeControlNamePart } from '../edit-control/utils';

type CreateFromTemplateProps = {
  agentId: string;
  agentName: string;
  onClose: () => void;
  onSuccess: () => void;
};

type Step = 'paste' | 'fill';

function parseTemplateJson(text: string): TemplateDefinition | string {
  if (!text.trim()) return 'Paste a template definition JSON to continue.';
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return 'Invalid JSON. Fix syntax errors and try again.';
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return 'Template must be a JSON object.';
  }
  const obj = parsed as Record<string, unknown>;
  if (!obj.definition_template) {
    return 'Missing required field "definition_template".';
  }
  if (
    typeof obj.definition_template !== 'object' ||
    obj.definition_template === null
  ) {
    return '"definition_template" must be a JSON object.';
  }
  // parameters is optional (defaults to empty dict on the server)
  if (obj.parameters !== undefined) {
    if (
      typeof obj.parameters !== 'object' ||
      obj.parameters === null ||
      Array.isArray(obj.parameters)
    ) {
      return '"parameters" must be a JSON object.';
    }
  }
  return parsed as TemplateDefinition;
}

function buildDefaultValues(
  template: TemplateDefinition
): Record<string, TemplateValue> {
  const defaults: Record<string, TemplateValue> = {};
  for (const [name, param] of Object.entries(template.parameters ?? {})) {
    if (param.default != null) {
      defaults[name] = param.default as TemplateValue;
    } else if (param.type === 'boolean') {
      defaults[name] = false;
    }
  }
  return defaults;
}

export function CreateFromTemplate({
  agentId,
  agentName,
  onClose,
  onSuccess,
}: CreateFromTemplateProps) {
  const [step, setStep] = useState<Step>('paste');
  const [jsonText, setJsonText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [template, setTemplate] = useState<TemplateDefinition | null>(null);
  const [templateValues, setTemplateValues] = useState<
    Record<string, TemplateValue>
  >({});
  const [controlName, setControlName] = useState('');
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});
  const [apiError, setApiError] = useState<ProblemDetail | null>(null);

  const addControlToAgent = useAddControlToAgent();

  const handleContinue = () => {
    const result = parseTemplateJson(jsonText);
    if (typeof result === 'string') {
      setParseError(result);
      return;
    }
    setParseError(null);
    setTemplate(result);
    setTemplateValues(buildDefaultValues(result));
    setControlName(
      `template-control-for-${sanitizeControlNamePart(agentName)}`
    );
    setStep('fill');
  };

  const handleBack = () => {
    setStep('paste');
    setParamErrors({});
    setApiError(null);
  };

  const handlePreviewErrors = useCallback((errors: Record<string, string>) => {
    setParamErrors(errors);
  }, []);

  const handleSave = () => {
    if (!template) return;
    if (!controlName.trim()) return;

    const templateInput: TemplateControlInput = {
      template,
      template_values: templateValues,
    };

    openActionConfirmModal({
      title: 'Create control?',
      children: (
        <Text size="sm" c="dimmed">
          This will create a template-backed control and add it to the agent.
        </Text>
      ),
      onConfirm: async () => {
        setApiError(null);
        try {
          await addControlToAgent.mutateAsync({
            agentId,
            controlName: controlName.trim(),
            definition: templateInput as never,
          });
          notifications.show({
            title: 'Control created',
            message: `"${controlName.trim()}" has been added to this agent.`,
            color: 'green',
          });
          onSuccess();
        } catch (error) {
          if (isApiError(error)) {
            const pd = error.problemDetail;
            setApiError(pd);
            if (pd.errors) {
              const newParamErrors: Record<string, string> = {};
              for (const item of pd.errors) {
                if (item.field?.startsWith('template_values.')) {
                  const paramName = item.field.replace('template_values.', '');
                  newParamErrors[paramName] = item.message;
                }
              }
              if (Object.keys(newParamErrors).length > 0) {
                setParamErrors(newParamErrors);
              }
            }
          } else {
            notifications.show({
              title: 'Failed to create control',
