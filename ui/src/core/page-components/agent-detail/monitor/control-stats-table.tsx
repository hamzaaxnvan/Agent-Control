'use client';

import { Badge, Card, Group, Table, Text } from '@mantine/core';
import { DataPill } from '@rungalileo/jupiter-ds';

import type { ControlStats } from '@/core/hooks/query-hooks/use-agent-monitor';

type ControlStatsTableProps = {
  stats: ControlStats[];
};

export function ControlStatsTable({ stats }: ControlStatsTableProps) {
  return (
    <Card withBorder p="md">
      <Table.ScrollContainer minWidth={800}>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Control</Table.Th>
              <Table.Th>Executions</Table.Th>
              <Table.Th>Triggers</Table.Th>
              <Table.Th>Errors</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {stats.map((control) => {
              const triggerRate =
                control.execution_count > 0
                  ? (control.match_count / control.execution_count) * 100
                  : 0;

              return (
                <Table.Tr key={control.control_id}>
                  <Table.Td>
                    <Text fw={500} size="sm">
                      {control.control_name}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {control.execution_count.toLocaleString()}
