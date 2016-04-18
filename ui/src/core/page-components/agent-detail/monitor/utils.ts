import type { TimeRangeType } from '@rungalileo/jupiter-ds';

import type { TimeRange } from '@/core/hooks/query-hooks/use-agent-monitor';

// Map Jupiter DS TimeRangeType to API TimeRange
// API supports: 1m, 5m, 15m, 1h, 24h, 7d, 30d, 180d, 365d
export function mapTimeRangeTypeToTimeRange(type: TimeRangeType): TimeRange {
  const mapping: Record<TimeRangeType, TimeRange> = {
    last5Mins: '5m',
    last15Mins: '15m',
