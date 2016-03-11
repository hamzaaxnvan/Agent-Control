'use client';

import { LineChart } from '@mantine/charts';
import {
  Box,
  Card,
  Grid,
  Group,
  RingProgress,
  SimpleGrid,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import React, { useEffect, useMemo, useState } from 'react';

import type { TimeseriesBucket } from '@/core/hooks/query-hooks/use-agent-monitor';

import type { SummaryMetrics } from './types';

type SummaryCardProps = {
  summary: SummaryMetrics;
  timeseries?: TimeseriesBucket[] | null;
  timeRange: string;
};

// Format timestamp based on time range
function formatTimestamp(timestamp: string, timeRange: string): string {
  const date = new Date(timestamp);

  if (['1m', '5m', '15m', '1h'].includes(timeRange)) {
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  if (timeRange === '24h') {
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });
}

// Metric card component - uses neutral background with colored left border accent
function MetricCard({
  label,
  value,
  tooltip,
  percentage,
}: {
  label: string;
  value: number;
  tooltip?: string;
  percentage?: number;
}) {
  const content = (
    <Box
      p="xs"
      style={{
        borderRadius: 'var(--mantine-radius-md)',
        backgroundColor: 'var(--mantine-color-default)',
        border: '1px solid var(--mantine-color-default-border)',
      }}
    >
      <Stack gap={2}>
        <Text size="xs" fw={500} c="var(--mantine-color-text)">
          {label}
        </Text>
        <Text size="md" fw={700} c="var(--mantine-color-text)">
          {value.toLocaleString()}
        </Text>
        {percentage !== undefined && (
          <Text size="xs" c="dimmed">
            {percentage.toFixed(1)}%
          </Text>
        )}
      </Stack>
    </Box>
  );

  if (tooltip) {
    return <Tooltip label={tooltip}>{content}</Tooltip>;
  }
  return content;
}

// Custom hook for animating a value from 0 to 1
function useAnimatedProgress(dependencies: unknown[], duration = 1000) {
  const [progress, setProgress] = useState(0);
  const animationRef = React.useRef<number | undefined>(undefined);
  const startTimeRef = React.useRef<number | undefined>(undefined);

  useEffect(() => {
    // Start fresh animation
    startTimeRef.current = Date.now();

    const animate = () => {
