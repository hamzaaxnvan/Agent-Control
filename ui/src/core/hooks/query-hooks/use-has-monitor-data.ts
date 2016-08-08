import type { TimeRangeValue } from '@rungalileo/jupiter-ds';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { TimeRange } from '@/core/hooks/query-hooks/use-agent-monitor';
import { mapTimeRangeTypeToTimeRange } from '@/core/page-components/agent-detail/monitor/utils';

const TIME_RANGE_STORAGE_KEY = 'agent-control-time-range-preference';

/**
 * Get stored time range from localStorage, defaulting to "7d"
 */
function getStoredTimeRange(): TimeRange {
  if (typeof window === 'undefined') return '7d';

  try {
    const stored = localStorage.getItem(TIME_RANGE_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as TimeRangeValue;
      if (parsed && typeof parsed.type === 'string') {
        return mapTimeRangeTypeToTimeRange(parsed.type);
      }
    }
  } catch {
    // Ignore parse errors
  }
  return '7d'; // Default
