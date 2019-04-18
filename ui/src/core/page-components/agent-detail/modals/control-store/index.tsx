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
