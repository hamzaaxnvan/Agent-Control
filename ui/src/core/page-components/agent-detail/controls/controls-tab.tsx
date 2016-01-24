import { Alert, Box, Center, Loader, Paper, Stack, Text } from '@mantine/core';
import { Button, Table } from '@rungalileo/jupiter-ds';
import { IconAlertCircle, IconInbox } from '@tabler/icons-react';
import { type ColumnDef } from '@tanstack/react-table';

import type { Control } from '@/core/api/types';

type ControlsTabProps = {
  controls: Control[];
  controlsLoading: boolean;
  controlsError: Error | null;
  columns: ColumnDef<Control>[];
  onAddControl: () => void;
};

export function ControlsTab({
  controls,
  controlsLoading,
  controlsError,
  columns,
  onAddControl,
}: ControlsTabProps) {
  if (controlsLoading) {
    return (
      <Center py="xl">
        <Stack align="center" gap="md">
          <Loader size="md" />
          <Text c="dimmed">Loading controls...</Text>
        </Stack>
      </Center>
    );
  }

  if (controlsError) {
    return (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title="Error loading controls"
        color="red"
      >
        Failed to fetch controls. Please try again later.
