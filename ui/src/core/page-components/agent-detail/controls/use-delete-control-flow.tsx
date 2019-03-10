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
}: UseDeleteControlFlowParams) {
  const removeControlFromAgent = useRemoveControlFromAgent();

  const handleDeleteControl = (control: Control) => {
    openDestructiveConfirmModal({
      title: 'Remove control from agent?',
      children: (
        <Text size="sm" c="dimmed">
          Remove &quot;{control.name}&quot; from this agent? This only removes
          the direct association from this agent and does not delete the control
          globally.
        </Text>
      ),
      onConfirm: () =>
        removeControlFromAgent.mutate(
          {
            agentId,
            controlId: control.id,
          },
          {
            onSuccess: (result: RemoveControlFromAgentResult) => {
