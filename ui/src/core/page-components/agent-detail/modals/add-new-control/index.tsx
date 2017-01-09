import {
  Box,
  Divider,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { Button, Table } from '@rungalileo/jupiter-ds';
import { IconAlertCircle, IconSearch, IconX } from '@tabler/icons-react';
import { type ColumnDef } from '@tanstack/react-table';
import { useMemo, useState } from 'react';

import { ErrorBoundary } from '@/components/error-boundary';
import type { EvaluatorInfo } from '@/core/api/types';
import { MODAL_NAMES, SUBMODAL_NAMES } from '@/core/constants/modal-routes';
import { getEvaluator } from '@/core/evaluators';
import { useEvaluators } from '@/core/hooks/query-hooks/use-evaluators';
import { useModalRoute } from '@/core/hooks/use-modal-route';

import { EditControlContent } from '../edit-control/edit-control-content';
import { sanitizeControlNamePart } from '../edit-control/utils';

type EvaluatorWithId = EvaluatorInfo & { id: string };

/**
 * Default evaluator configs for each evaluator type
 * Based on backend models in agent_control_models/controls.py
 */
const DEFAULT_EVALUATOR_CONFIGS: Record<string, Record<string, unknown>> = {
  regex: {
    pattern: '^.*$',
  },
  list: {
    values: [],
    logic: 'any',
    match_on: 'match',
    match_mode: 'exact',
    case_sensitive: false,
  },
  'galileo.luna': {
    scorer_label: '',
    scorer_id: '',
    scorer_version_id: '',
    threshold: 0.5,
    operator: 'gte',
    payload_field: 'input',
    timeout_ms: 10000,
    config: null,
  },
  'defenseclaw.rule_pack': {
    schema_version: 1,
    rule_pack: {
      version: 1,
      category: 'agent-control',
      rules: [
        {
          id: '',
          pattern: '',
          title: '',
          severity: 'HIGH',
          confidence: 0.99,
          tags: [],
        },
      ],
    },
  },
  'defenseclaw.opa_policy': {
    schema_version: 1,
    policy: {
      domain: 'guardrail',
      block_at: 'HIGH',
      alert_at: 'MEDIUM',
      cisco_trust_level: 'full',
    },
  },
};

function getDefaultConfigForEvaluator(
  evaluatorId: string
): Record<string, unknown> {
  return DEFAULT_EVALUATOR_CONFIGS[evaluatorId] ?? {};
}

function buildJsonDraftControl() {
  return {
    id: 0,
    name: 'new-json-control',
    control: {
      description: '',
      enabled: true,
      execution: 'server' as const,
      scope: {
        step_types: ['llm'],
        stages: ['post'] as ('post' | 'pre')[],
      },
      condition: {
        selector: {
          path: '*',
        },
        evaluator: {
          name: 'regex',
          config: getDefaultConfigForEvaluator('regex'),
        },
      },
      action: { decision: 'deny' as const },
      tags: [],
    },
  };
}

type AddNewControlModalProps = {
  opened: boolean;
  onClose: () => void;
  agentId: string;
};

export function AddNewControlModal({
  opened,
  onClose,
  agentId,
}: AddNewControlModalProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const { submodal, evaluator, openModal, closeSubmodal, closeModal } =
    useModalRoute();
  const { data: evaluatorsData, isLoading, error } = useEvaluators();

  // Derive submodal open state from URL
  const editModalOpened = submodal === SUBMODAL_NAMES.CREATE;

  // Find selected evaluator from URL or state
  const selectedEvaluator = useMemo(() => {
    if (evaluator && evaluatorsData) {
      const evaluatorData = evaluatorsData[evaluator];
      if (evaluatorData) {
        return { ...evaluatorData, id: evaluator };
      }
    }
    return null;
  }, [evaluator, evaluatorsData]);

  const handleAddClick = (evaluator: EvaluatorWithId) => {
    openModal(MODAL_NAMES.CONTROL_STORE, {
      submodal: SUBMODAL_NAMES.CREATE,
      evaluator: evaluator.id,
    });
  };

  const handleFromJsonClick = () => {
    openModal(MODAL_NAMES.CONTROL_STORE, {
      submodal: SUBMODAL_NAMES.CREATE,
    });
  };

  const handleEditModalClose = () => {
    closeSubmodal();
  };

  const handleEditModalSuccess = () => {
    // Close all modals on successful create
    // Use closeModal to close the entire modal stack (control-store + add-new + create)
    closeModal();
  };

  // Transform evaluators record to array for table display
  const evaluators = useMemo(() => {
    if (!evaluatorsData) return [];
    return Object.entries(evaluatorsData).map(([key, evaluator]) => ({
      ...evaluator,
      id: key,
    }));
  }, [evaluatorsData]);

  const draftControl = useMemo(() => {
    if (selectedEvaluator) {
      const evaluatorDefinition = getEvaluator(selectedEvaluator.id);
      const name = `new-${sanitizeControlNamePart(selectedEvaluator.name)}-control`;
      return {
        id: 0,
        name,
        control: {
          description: selectedEvaluator.description,
          enabled: true,
          execution: evaluatorDefinition?.defaultExecution ?? 'server',
          scope: {
            step_types: ['llm'],
            stages: ['post'] as ('post' | 'pre')[],
          },
          condition: {
            selector: {
              path: '*',
            },
            evaluator: {
              name: selectedEvaluator.id,
              config: getDefaultConfigForEvaluator(selectedEvaluator.id),
            },
