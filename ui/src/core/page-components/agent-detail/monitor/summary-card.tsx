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
      const elapsed = Date.now() - (startTimeRef.current || Date.now());
      const rawProgress = Math.min(elapsed / duration, 1);
      // Ease-out cubic for smooth deceleration
      const eased = 1 - Math.pow(1 - rawProgress, 3);
      setProgress(eased);

      if (rawProgress < 1) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };

    // Start from 0 by immediately setting and then animating
    setProgress(0);
    // Use setTimeout to ensure the 0 is rendered before animating
    const timeoutId = setTimeout(() => {
      animationRef.current = requestAnimationFrame(animate);
    }, 16);

    return () => {
      clearTimeout(timeoutId);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);

  return progress;
}

export function SummaryCard({
  summary,
  timeseries,
  timeRange,
}: SummaryCardProps) {
  // Animation progress for RingProgress (0 to 1)
  const ringAnimationProgress = useAnimatedProgress(
    [timeRange, summary.totalMatches],
    1000
  );

  // Transform timeseries data for Mantine charts
  const chartData = useMemo(() => {
    if (!timeseries) return [];
    return timeseries.map((bucket) => ({
      timestamp: formatTimestamp(bucket.timestamp, timeRange),
      Triggers: bucket.match_count,
      Errors: bucket.error_count,
    }));
  }, [timeseries, timeRange]);

  // Check if there's any chart data to display
  const hasChartData =
    timeseries &&
    timeseries.some(
      (bucket) => bucket.match_count > 0 || bucket.error_count > 0
    );

  return (
    <Card withBorder p="lg" radius="md">
      <Stack gap="lg">
        {/* Top: Metrics Row */}
        <SimpleGrid cols={3} spacing="md">
          <MetricCard
            label="Executions"
            value={summary.totalExecutions}
            tooltip="Total control evaluations"
          />
          <MetricCard
            label="Triggers"
            value={summary.totalMatches}
            tooltip="Controls that matched (triggered action)"
            percentage={
              summary.totalExecutions > 0
                ? (summary.totalMatches / summary.totalExecutions) * 100
                : undefined
            }
          />
          <MetricCard
            label="Errors"
            value={summary.totalErrors}
            tooltip="Errors during control evaluation"
          />
        </SimpleGrid>

        {/* Bottom: Chart + Actions Distribution */}
        <Grid gutter="lg">
          {/* Left: Trend Chart */}
          <Grid.Col span={8}>
            <Box
              p="md"
              style={{
                borderRadius: 'var(--mantine-radius-sm)',
                backgroundColor: 'var(--mantine-color-default)',
                border: '1px solid var(--mantine-color-default-border)',
                height: '100%',
              }}
            >
              <Stack gap="sm" h="100%">
                <Group justify="space-between" align="center">
                  <Text size="sm" fw={600}>
                    Activity Trend
                  </Text>
                  {/* Compact Legend */}
                  <Group gap="md">
                    <Group gap={4}>
