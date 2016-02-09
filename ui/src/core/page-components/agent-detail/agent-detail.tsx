import {
  Alert,
  Box,
  Center,
  Group,
  Loader,
  Modal,
  Stack,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { Button, TimeRangeSwitch } from '@rungalileo/jupiter-ds';
import { IconAlertCircle, IconChartBar, IconShield } from '@tabler/icons-react';
import { useRouter } from 'next/router';
import React, { useMemo, useRef, useState } from 'react';

import { ErrorBoundary } from '@/components/error-boundary';
import type { Control } from '@/core/api/types';
import { SearchInput } from '@/core/components/search-input';
import { getAgentRoute } from '@/core/constants/agent-routes';
import { MODAL_NAMES } from '@/core/constants/modal-routes';
import { useAgent } from '@/core/hooks/query-hooks/use-agent';
import { useAgentControls } from '@/core/hooks/query-hooks/use-agent-controls';
import { useHasMonitorData } from '@/core/hooks/query-hooks/use-has-monitor-data';
import { useUpdateControl } from '@/core/hooks/query-hooks/use-update-control';
import { useUpdateControlMetadata } from '@/core/hooks/query-hooks/use-update-control-metadata';
import { useModalRoute } from '@/core/hooks/use-modal-route';
import { useQueryParam } from '@/core/hooks/use-query-param';
import { useTimeRangePreference } from '@/core/hooks/use-time-range-preference';

import { ControlsTab } from './controls/controls-tab';
import { useControlsTableColumns } from './controls/table-columns';
import { useDeleteControlFlow } from './controls/use-delete-control-flow';
import { ControlStoreModal } from './modals/control-store';
import { EditControlContent } from './modals/edit-control/edit-control-content';
import { AgentsMonitor, TIME_RANGE_SEGMENTS } from './monitor';

type AgentDetailPageProps = {
  agentId: string;
  defaultTab?: 'controls' | 'monitor';
};

const AgentDetailPage = ({ agentId, defaultTab }: AgentDetailPageProps) => {
  const router = useRouter();
  const { modal, controlId, openModal, closeModal } = useModalRoute();
  const [selectedControl, setSelectedControl] = useState<Control | null>(null);
  const [searchQuery] = useQueryParam('q');
  const [timeRangeValue, setTimeRangeValue] = useTimeRangePreference();

  const controlStoreOpened = modal === MODAL_NAMES.CONTROL_STORE;
  const editModalOpened = modal === MODAL_NAMES.EDIT;

  const {
    data: agent,
    isLoading: agentLoading,
    error: agentError,
  } = useAgent(agentId);
  const {
    data: controlsResponse,
    isLoading: controlsLoading,
    error: controlsError,
  } = useAgentControls(agentId);

  const needsInitialTabCheck = !defaultTab;
  const { data: hasMonitorData, isLoading: checkingMonitorData } =
    useHasMonitorData(agentId, {
      enabled: needsInitialTabCheck,
    });

  const updateControl = useUpdateControl();
  const updateControlMetadata = useUpdateControlMetadata();
  const editCloseRef = useRef<(() => void) | null>(null);

  const handleCloseEditModal = () => {
    // If EditControlContent has registered a close handler (with dirty check),
    // use it. Otherwise close directly.
    if (editCloseRef.current) {
      editCloseRef.current();
      return;
    }
    closeModal();
  };

  const { handleDeleteControl, removeControlFromAgent } = useDeleteControlFlow({
    agentId,
    selectedControl,
    onCloseEditModal: handleCloseEditModal,
  });

  const [activeTab, setActiveTab] = useState<string | null>(() => {
    if (defaultTab === 'monitor') return 'monitor';
    if (defaultTab === 'controls') return 'controls';
    return 'controls';
  });

  const hasCheckedInitialTab = React.useRef(false);
  React.useEffect(() => {
    if (!defaultTab && !hasCheckedInitialTab.current && !checkingMonitorData) {
      hasCheckedInitialTab.current = true;
      if (hasMonitorData) {
        setActiveTab('monitor');
        router.replace(
          getAgentRoute(agentId, { tab: 'monitor', query: router.query }),
          undefined,
          {
            shallow: true,
          }
        );
      } else {
        setActiveTab('controls');
        router.replace(
          getAgentRoute(agentId, { tab: 'controls', query: router.query }),
          undefined,
          {
            shallow: true,
          }
        );
      }
    }
  }, [defaultTab, checkingMonitorData, hasMonitorData, agentId, router]);

  const controls = useMemo(() => {
    const allControls = controlsResponse?.controls || [];
    if (!searchQuery.trim()) return allControls;
    const query = searchQuery.toLowerCase();
    return allControls.filter(
      (control) =>
        control.name.toLowerCase().includes(query) ||
        control.control?.description?.toLowerCase().includes(query)
    );
  }, [controlsResponse, searchQuery]);

  // Sync selectedControl to URL controlId when edit modal is open.
  // We do not clear selectedControl on close so modal content stays mounted
  // during the close animation (avoids content disappearing before title/backdrop).
  React.useEffect(() => {
    if (!editModalOpened || !controlId || !controlsResponse?.controls) return;
    const control = controlsResponse.controls.find(
      (c) => c.id.toString() === controlId
    );
    setSelectedControl(control ?? null);
  }, [editModalOpened, controlId, controlsResponse]);

  const handleEditControl = (control: Control) => {
    openModal(MODAL_NAMES.EDIT, { controlId: control.id.toString() });
  };

  const columns = useControlsTableColumns({
    agentId,
    updateControl,
    updateControlMetadata,
    removeControlFromAgent,
    onEditControl: handleEditControl,
    onDeleteControl: handleDeleteControl,
  });

  if (agentLoading) {
