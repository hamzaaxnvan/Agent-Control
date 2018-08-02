import {
  Alert,
  Box,
  Divider,
  Grid,
  Group,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { Button } from '@rungalileo/jupiter-ds';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { JsonEditorMonaco } from '@/components/json-editor-monaco';
import { isApiError } from '@/core/api/errors';
import type {
  Control,
  ControlDefinition,
  ProblemDetail,
} from '@/core/api/types';
import { useAddControlToAgent } from '@/core/hooks/query-hooks/use-add-control-to-agent';
import { useAgent } from '@/core/hooks/query-hooks/use-agent';
import { useControlSchema } from '@/core/hooks/query-hooks/use-control-schema';
import { useEvaluators } from '@/core/hooks/query-hooks/use-evaluators';
import { useUpdateControl } from '@/core/hooks/query-hooks/use-update-control';
import { useUpdateControlMetadata } from '@/core/hooks/query-hooks/use-update-control-metadata';
import { useValidateControlData } from '@/core/hooks/query-hooks/use-validate-control-data';
import {
  openActionConfirmModal,
  openDestructiveConfirmModal,
} from '@/core/utils/modals';

import { ApiErrorAlert } from './api-error-alert';
import {
  buildEditableCondition,
  getControlConditionState,
} from './control-condition';
import { ControlDefinitionForm } from './control-definition-form';
import { EvaluatorConfigSection } from './evaluator-config-section';
import { TemplateEditContent } from './template-edit-content';
import type {
  ControlDefinitionFormValues,
  ControlEditorMode,
  EditControlMode,
  JsonEditorEvaluatorOption,
} from './types';
import { useEvaluatorConfigState } from './use-evaluator-config-state';
import { applyApiErrorsToForms } from './utils';

function isTemplateBacked(control: Control): boolean {
  const def = control.control as Record<string, unknown> | undefined;
  return def?.template != null;
}

const EVALUATOR_CONFIG_HEIGHT = 450;
const JSON_EDITOR_HEIGHT = 520;
type ValidationStatus = 'idle' | 'validating' | 'valid' | 'invalid';

const DEFAULT_CONTROL_TEMPLATE = JSON.stringify(
  {
    description: 'Block outputs containing US Social Security Numbers',
    enabled: true,
    execution: 'server',
    scope: {
      step_types: ['llm'],
      stages: ['post'],
    },
    condition: {
      selector: { path: 'output' },
      evaluator: {
        name: 'regex',
        config: { pattern: '\\b\\d{3}-\\d{2}-\\d{4}\\b' },
      },
    },
    action: { decision: 'deny' },
    tags: ['pii', 'compliance'],
  },
  null,
  2
);

export type EditControlContentProps = {
  /** The control to edit/create template */
  control: Control;
  /** Agent ID for invalidating queries on save */
  agentId: string;
  /** Mode: 'create' for new control, 'edit' for existing */
  mode?: EditControlMode;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when save succeeds */
  onSuccess?: () => void;
  /** Initial editor mode */
  initialEditorMode?: ControlEditorMode;
  /**
   * Mutable ref that receives the close handler (with unsaved-changes check).
   * The parent Modal can use this ref for its own onClose so the X button
   * also triggers the dirty check.
   */
  onCloseRef?: React.MutableRefObject<(() => void) | null>;
};

export const EditControlContent = (props: EditControlContentProps) => {
  // Template-backed controls use a dedicated editor in edit mode
  if (props.mode !== 'create' && isTemplateBacked(props.control)) {
    return (
      <TemplateEditContent
        key={props.control.id}
        control={props.control}
        agentId={props.agentId}
        onClose={props.onClose}
        onSuccess={props.onSuccess}
      />
    );
  }

  return <RawEditControlContent {...props} />;
};

const RawEditControlContent = ({
  control,
  agentId,
  mode = 'edit',
  onClose,
  onSuccess,
  initialEditorMode = 'form',
  onCloseRef,
}: EditControlContentProps) => {
  const { data: agentResponse } = useAgent(agentId);
  const { data: controlSchemaResponse } = useControlSchema();
  const { data: globalEvaluators } = useEvaluators();
  const steps = agentResponse?.steps ?? [];
  const agentName = agentResponse?.agent?.agent_name ?? agentId;

  const [workingDefinition, setWorkingDefinition] = useState<ControlDefinition>(
    control.control
  );
  const [editorMode, setEditorMode] =
    useState<ControlEditorMode>(initialEditorMode);
  const [apiError, setApiError] = useState<ProblemDetail | null>(null);
  const [unmappedErrors, setUnmappedErrors] = useState<
    Array<{ field: string | null; message: string }>
  >([]);
  const [definitionJsonText, setDefinitionJsonText] = useState('');
  const [definitionJsonError, setDefinitionJsonError] = useState<string | null>(
    null
  );
  const [definitionValidationError, setDefinitionValidationError] =
    useState<ProblemDetail | null>(null);
  const [definitionValidationStatus, setDefinitionValidationStatus] =
    useState<ValidationStatus>('idle');
  const [isDirty, setIsDirty] = useState(false);

  const updateControl = useUpdateControl();
  const updateControlMetadata = useUpdateControlMetadata();
  const addControlToAgent = useAddControlToAgent();
  const { mutateAsync: validateControlDataAsync } = useValidateControlData();
  const isCreating = mode === 'create';
  const isPending = isCreating
    ? addControlToAgent.isPending
    : updateControl.isPending || updateControlMetadata.isPending;

  const formRef = useRef<HTMLFormElement>(null);
  const formInitializedForEvaluator = useRef<string>('');
  const { leafCondition, evaluatorId, evaluator, canEditLeafCondition } =
    useMemo(
      () => getControlConditionState(workingDefinition),
      [workingDefinition]
    );
  const availableEvaluators = useMemo<JsonEditorEvaluatorOption[]>(() => {
    const merged = new Map<string, JsonEditorEvaluatorOption>();

    for (const [id, evaluatorInfo] of Object.entries(globalEvaluators ?? {})) {
      merged.set(id, {
        id,
        label: evaluatorInfo.name,
        description: evaluatorInfo.description,
        source: 'global',
        configSchema: evaluatorInfo.config_schema,
      });
    }

    for (const evaluatorSchema of agentResponse?.evaluators ?? []) {
      const id = `${agentName}:${evaluatorSchema.name}`;
      merged.set(id, {
        id,
        label: evaluatorSchema.name,
        description: evaluatorSchema.description,
        source: 'agent',
        configSchema: evaluatorSchema.config_schema,
      });
    }

    return [...merged.values()];
  }, [agentName, agentResponse?.evaluators, globalEvaluators]);
  const activeEvaluatorOption = useMemo(
    () =>
      availableEvaluators.find((candidate) => candidate.id === evaluatorId) ??
      null,
    [availableEvaluators, evaluatorId]
  );
  const installedEvaluatorSupportedExecutions =
    activeEvaluatorOption?.source === 'global'
      ? evaluator?.supportedExecutions
      : undefined;

  const definitionForm = useForm<ControlDefinitionFormValues>({
    initialValues: {
      name: '',
      description: '',
      enabled: true,
      step_types: ['llm'],
      stages: ['post'],
      step_names: '',
      step_name_regex: '',
      step_name_mode: 'names',
      selector_path: '*',
      action_decision: 'deny',
      action_steering_context: '',
      execution: 'server',
    },
    validate: {
      name: (value) => (!value?.trim() ? 'Control name is required' : null),
      execution: (value) =>
        installedEvaluatorSupportedExecutions?.includes(value)
          ? null
          : installedEvaluatorSupportedExecutions
            ? `This evaluator only supports: ${installedEvaluatorSupportedExecutions.join(', ')}`
            : null,
      selector_path: (value) => {
        if (editorMode === 'json' || !canEditLeafCondition) {
          return null;
        }
        if (!value?.trim()) {
          return 'Selector path is required';
        }
        const validRoots = ['input', 'output', 'name', 'type', 'context', '*'];
        const root = value.split('.')[0];
        if (!validRoots.includes(root)) {
          return `Invalid path root '${root}'. Must be one of: ${validRoots.join(', ')}`;
        }
        return null;
      },
    },
  });

  const evaluatorForm = useForm({
    initialValues: evaluator?.initialValues ?? {},
    validate: evaluator?.validate,
  });

  const getEvaluatorConfig = useCallback(() => {
    if (!leafCondition) {
      return {};
    }
    if (!evaluator) {
      return leafCondition.evaluatorConfig;
    }
    if (formInitializedForEvaluator.current !== evaluatorId) {
      return evaluator.toConfig(evaluator.initialValues);
    }
    return evaluator.toConfig(evaluatorForm.values);
  }, [evaluator, evaluatorForm.values, evaluatorId, leafCondition]);

  const syncJsonToForm = useCallback(
    (config: Record<string, unknown>) => {
      if (evaluator) {
        evaluatorForm.setValues(evaluator.fromConfig(config));
      }
    },
    [evaluator, evaluatorForm]
  );

  const buildLeafCondition = useCallback(
    (
      values: ControlDefinitionFormValues,
      finalConfig: Record<string, unknown>
    ): ControlDefinition['condition'] => {
      return buildEditableCondition(
        workingDefinition,
        leafCondition,
        values.selector_path.trim(),
        finalConfig
      );
    },
    [leafCondition, workingDefinition]
  );

  const buildControlDefinition = useCallback(
    (
      values: ControlDefinitionFormValues,
      condition: ControlDefinition['condition']
    ): ControlDefinition => {
      const stepTypes = values.step_types
        .map((value) => value.trim())
        .filter(Boolean);
      const stepNames = values.step_names
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean);
      const stepNameRegex = values.step_name_regex.trim();
      const isRegexMode = values.step_name_mode === 'regex';

      const scope: Record<string, unknown> = {};
      if (stepTypes.length > 0) scope.step_types = stepTypes;
      if (!isRegexMode && stepNames.length > 0) scope.step_names = stepNames;
      if (isRegexMode && stepNameRegex) scope.step_name_regex = stepNameRegex;
      if (values.stages.length > 0) scope.stages = values.stages;

      return {
        description: values.description?.trim() || undefined,
        enabled: values.enabled,
        execution: values.execution,
        scope: Object.keys(scope).length > 0 ? scope : undefined,
        condition,
        action: {
          decision: values.action_decision,
          ...(values.action_decision === 'steer' &&
          values.action_steering_context?.trim()
            ? {
                steering_context: {
                  message: values.action_steering_context.trim(),
                },
              }
            : {}),
        },
        tags: workingDefinition.tags,
      };
    },
    [workingDefinition.tags]
  );

