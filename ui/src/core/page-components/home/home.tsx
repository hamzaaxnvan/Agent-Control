import { CodeHighlight } from '@mantine/code-highlight';
import {
  Alert,
  Anchor,
  Box,
  Center,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { Table } from '@rungalileo/jupiter-ds';
import { IconAlertCircle, IconExternalLink } from '@tabler/icons-react';
import { type ColumnDef } from '@tanstack/react-table';
import { useRouter } from 'next/router';
import { useMemo } from 'react';

import type { AgentSummary } from '@/core/api/types';
import { SearchInput } from '@/core/components/search-input';
import { getAgentRoute } from '@/core/constants/agent-routes';
import { useAgentsInfinite } from '@/core/hooks/query-hooks/use-agents-infinite';
import { useInfiniteScroll } from '@/core/hooks/use-infinite-scroll';
import { useQueryParam } from '@/core/hooks/use-query-param';

// Table row type - uses real API data
type AgentTableRow = AgentSummary;

function EmptyAgentsState() {
  return (
    <Center h={400}>
      <Stack align="center" gap="md" maw={600}>
        <Title order={3} fw={600}>
          No agents yet
        </Title>
        <Text size="sm" c="dimmed" ta="center">
          Get started by registering your first agent with the Python SDK. Once
          an agent connects to the control server, it will appear here.
        </Text>
        <Box w="100%">
          <CodeHighlight
