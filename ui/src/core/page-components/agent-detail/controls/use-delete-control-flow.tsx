import { Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';

import type { Control } from '@/core/api/types';
import {
  type RemoveControlFromAgentResult,
  useRemoveControlFromAgent,
} from '@/core/hooks/query-hooks/use-remove-control-from-agent';
import { openDestructiveConfirmModal } from '@/core/utils/modals';

type UseDeleteControlFlowParams = {
  agentId: string;
  selectedControl: Control | null;
  onCloseEditModal: () => void;
};

export function useDeleteControlFlow({
  agentId,
  selectedControl,
  onCloseEditModal,
