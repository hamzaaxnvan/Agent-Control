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
            language="python"
            code={`import agent_control
from agent_control import control, ControlViolationError

agent_control.init(
    agent_name="support-agent-v1",
    agent_description="Customer Support Agent",
    server_url="http://localhost:8000",
)

@control()
async def chat(message: str) -> str:
    return await llm.generate(message)`}
          />
        </Box>
        <Anchor
          href="https://github.com/agentcontrol/agent-control/blob/main/README.md"
          target="_blank"
          size="sm"
          c="blue"
          underline="hover"
        >
          <Group gap={4} align="center">
            <Text size="sm">View docs</Text>
            <IconExternalLink size={14} />
          </Group>
        </Anchor>
      </Stack>
    </Center>
  );
}

const HomePage = () => {
  const router = useRouter();
  // Get search value for debouncing (SearchInput handles the UI and URL sync)
  const [searchQuery] = useQueryParam('search');
  const [debouncedSearch] = useDebouncedValue(searchQuery, 300);

  // Server-side search via name param
  const {
    data,
    fetchNextPage,
