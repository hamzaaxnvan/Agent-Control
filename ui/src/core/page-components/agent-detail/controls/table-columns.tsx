import { ActionIcon, Badge, Box, Group, Switch, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconPencil, IconTrash } from '@tabler/icons-react';
import { type ColumnDef } from '@tanstack/react-table';
import { useMemo } from 'react';

import type { Control } from '@/core/api/types';
import type { useRemoveControlFromAgent } from '@/core/hooks/query-hooks/use-remove-control-from-agent';
import type { useUpdateControl } from '@/core/hooks/query-hooks/use-update-control';
import type { useUpdateControlMetadata } from '@/core/hooks/query-hooks/use-update-control-metadata';
import { openActionConfirmModal } from '@/core/utils/modals';

import { getStepTypeLabelAndColor } from './utils';

type UseControlsTableColumnsParams = {
  agentId: string;
  updateControl: ReturnType<typeof useUpdateControl>;
  updateControlMetadata: ReturnType<typeof useUpdateControlMetadata>;
  removeControlFromAgent: ReturnType<typeof useRemoveControlFromAgent>;
  onEditControl: (control: Control) => void;
  onDeleteControl: (control: Control) => void;
};

export function useControlsTableColumns({
  agentId,
  updateControl,
  updateControlMetadata,
  removeControlFromAgent,
  onEditControl,
  onDeleteControl,
}: UseControlsTableColumnsParams): ColumnDef<Control>[] {
  return useMemo(
    () => [
      {
        id: 'enabled',
        header: '',
        size: 60,
        cell: ({ row }: { row: { original: Control } }) => {
          const control = row.original;
          const enabled = control.control?.enabled ?? false;
          const ctrl = control.control as Record<string, unknown> | undefined;
          const isTemplate = ctrl?.template != null;
          return (
            <Switch
              checked={enabled}
              color="green.5"
              onChange={(e) => {
                const newEnabled = e.currentTarget.checked;
                openActionConfirmModal({
