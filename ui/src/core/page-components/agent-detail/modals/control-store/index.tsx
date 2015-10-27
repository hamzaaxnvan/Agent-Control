import {
  Anchor,
  Box,
  Divider,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { Button, Table } from '@rungalileo/jupiter-ds';
import { IconAlertCircle, IconX } from '@tabler/icons-react';
import { type ColumnDef } from '@tanstack/react-table';
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

import { ErrorBoundary } from '@/components/error-boundary';
import { api } from '@/core/api/client';
import type { ControlDefinition, ControlSummary } from '@/core/api/types';
import { SearchInput } from '@/core/components/search-input';
import { getAgentRoute } from '@/core/constants/agent-routes';
import { MODAL_NAMES, SUBMODAL_NAMES } from '@/core/constants/modal-routes';
import { useControlsInfinite } from '@/core/hooks/query-hooks/use-controls-infinite';
import { useInfiniteScroll } from '@/core/hooks/use-infinite-scroll';
import { useModalRoute } from '@/core/hooks/use-modal-route';
import { useQueryParam } from '@/core/hooks/use-query-param';

import { AddNewControlModal } from '../add-new-control';
import { EditControlContent } from '../edit-control/edit-control-content';
import { sanitizeControlNamePart } from '../edit-control/utils';

type ControlStoreModalProps = {
  opened: boolean;
  onClose: () => void;
  agentId: string;
};

export function ControlStoreModal({
  opened,
  onClose,
  agentId,
}: ControlStoreModalProps) {
  // Get search value for debouncing (SearchInput handles the UI and URL sync)
  const [searchQuery, setSearchQuery] = useQueryParam('store_q');
  const [debouncedSearch] = useDebouncedValue(searchQuery, 300);
  const {
    submodal,
    evaluator: _evaluator,
    controlId,
    openModal,
    closeSubmodal,
    closeModal,
  } = useModalRoute();
  const [selectedControl, setSelectedControl] = useState<{
    summary: ControlSummary;
    definition: ControlDefinition;
  } | null>(null);
  const [loadingControlId, setLoadingControlId] = useState<number | null>(null);

  // Derive submodal open state from URL
  const editModalOpened = submodal === SUBMODAL_NAMES.EDIT;
  // AddNewControlModal should be open when submodal is "add-new" OR "create" (create is nested inside add-new)
  const addNewModalOpened =
    submodal === SUBMODAL_NAMES.ADD_NEW || submodal === SUBMODAL_NAMES.CREATE;

  // Clear search query param when modal closes
  useEffect(() => {
    if (!opened && searchQuery) {
      setSearchQuery('');
    }
  }, [opened, searchQuery, setSearchQuery]);

  // Server-side search via name param - only fetch when modal is open
  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useControlsInfinite({
    name: debouncedSearch || undefined,
    enabled: opened,
  });

  // Infinite scroll setup
  const { sentinelRef, scrollContainerRef } = useInfiniteScroll({
    hasNextPage: hasNextPage ?? false,
    isFetchingNextPage,
    fetchNextPage,
  });

  // Flatten paginated data
  const controls = useMemo(() => {
    return data?.pages.flatMap((page) => page.controls) ?? [];
  }, [data]);

  // Ref callback to attach to Table's scroll container when maxHeight is set
  const tableWrapperRef = useRef<HTMLDivElement>(null);

  // Attach scroll container ref to the Table's scroll container
  // TODO: Revisit scroll container handling for control-store
  useEffect(() => {
    if (tableWrapperRef.current && controls.length > 0) {
      // Find the scrollable container (the div with overflow: auto from Table's maxHeight)
      // The Table component wraps content in a div with the "root" class when maxHeight is set
      const scrollContainer = tableWrapperRef.current.querySelector(
        '[class*="root"]'
      ) as HTMLElement;
      if (scrollContainer) {
        // Check if it's scrollable (has overflow: auto)
        const computedStyle = window.getComputedStyle(scrollContainer);
        if (
          computedStyle.overflow === 'auto' ||
          computedStyle.overflowY === 'auto'
        ) {
          (
            scrollContainerRef as React.MutableRefObject<HTMLElement | null>
          ).current = scrollContainer;

          // Append sentinel inside the scroll container (after the table)
          if (
            sentinelRef.current &&
            sentinelRef.current.parentElement !== scrollContainer
          ) {
            scrollContainer.appendChild(sentinelRef.current);
          }
        }
      }
    }
  }, [controls.length, scrollContainerRef, sentinelRef]);

  // Load control when controlId is in URL
  useEffect(() => {
    if (editModalOpened && controlId && !selectedControl) {
      const loadControl = async () => {
        const id = parseInt(controlId, 10);
        if (isNaN(id)) return;

        setLoadingControlId(id);
        try {
          const { data: controlData, error: fetchError } =
            await api.controls.getData(id);
          if (fetchError || !controlData?.data) {
            notifications.show({
              title: 'Error',
              message: 'Failed to load control configuration',
              color: 'red',
            });
            return;
          }
          // Find the control summary from the list
          const controlSummary = controls.find((c) => c.id === id);
          if (controlSummary) {
            setSelectedControl({
              summary: controlSummary,
              definition: controlData.data,
            });
          }
        } finally {
          setLoadingControlId(null);
        }
      };
      loadControl();
    }
  }, [editModalOpened, controlId, selectedControl, controls]);

  // Clear selectedControl when edit modal closes
  useEffect(() => {
    if (!editModalOpened && selectedControl) {
      setSelectedControl(null);
    }
  }, [editModalOpened, selectedControl]);

  const handleCopyControl = async (control: ControlSummary) => {
    openModal(MODAL_NAMES.CONTROL_STORE, {
      submodal: SUBMODAL_NAMES.EDIT,
      controlId: control.id.toString(),
    });
  };

  const handleEditModalClose = () => {
    closeSubmodal();
  };

  const handleEditModalSuccess = () => {
    // Close all modals on successful create/edit
    // Use closeModal to remove all modal query parameters from URL
    closeModal();
  };

  // Build a draft control for the edit modal with full evaluator config (clone: append -copy to name)
  const draftControl = useMemo(() => {
    if (!selectedControl) return null;
    const { summary, definition } = selectedControl;
    const sanitizedName = sanitizeControlNamePart(summary.name);
    return {
      id: 0,
      name: `${sanitizedName}-copy`,
      control: {
        ...definition,
        // Ensure we have the proper types
        execution: (definition.execution ?? 'server') as 'server' | 'sdk',
        scope: {
          ...definition.scope,
          stages: (definition.scope?.stages ?? ['post']) as ('post' | 'pre')[],
        },
      },
    };
  }, [selectedControl]);

  const columns: ColumnDef<ControlSummary>[] = [
    {
      id: 'enabled',
      header: '',
      accessorKey: 'enabled',
      size: 40,
      cell: ({ row }) => (
        <Group justify="center">
          <Tooltip label={row.original.enabled ? 'Enabled' : 'Disabled'}>
            <Box
              style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                backgroundColor: row.original.enabled
                  ? 'var(--mantine-color-green-6)'
                  : 'var(--mantine-color-gray-5)',
              }}
            />
          </Tooltip>
        </Group>
      ),
    },
    {
      id: 'name',
      header: 'Name',
      accessorKey: 'name',
      size: 260,
      cell: ({ row }) => (
        <Text size="sm" fw={500}>
          {row.original.name}
        </Text>
      ),
    },
    {
      id: 'description',
      header: 'Description',
      accessorKey: 'description',
      size: 200,
      cell: ({ row }) => (
        <Tooltip
          label={row.original.description}
          withArrow
          disabled={!row.original.description}
        >
          <Text size="sm" c="dimmed" lineClamp={1}>
            {row.original.description || '—'}
          </Text>
        </Tooltip>
      ),
    },
    {
      id: 'agent',
      header: 'Used by',
      size: 150,
      cell: ({ row }) => {
        const usedByAgent = row.original.used_by_agent;
        if (!usedByAgent) {
          return (
            <Text size="sm" c="dimmed">
              —
            </Text>
          );
        }

        const controlName = row.original.name;
