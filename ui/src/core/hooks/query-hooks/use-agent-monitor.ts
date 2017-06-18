import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { components } from '@/core/api/generated/api-types';

export type TimeRange =
  | '1m'
  | '5m'
  | '15m'
  | '1h'
  | '24h'
  | '7d'
  | '30d'
  | '180d'
  | '365d';
export type ControlStats = components['schemas']['ControlStats'];
export type StatsResponse = components['schemas']['StatsResponse'];
export type TimeseriesBucket = components['schemas']['TimeseriesBucket'];
export type StatsTotals = components['schemas']['StatsTotals'];

export function useAgentMonitor(
  agentName: string,
  timeRange: TimeRange = '1h',
  options?: {
    enabled?: boolean;
    refetchInterval?: number;
    includeTimeseries?: boolean;
