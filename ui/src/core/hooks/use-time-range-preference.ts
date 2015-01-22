import type { TimeRangeValue } from '@rungalileo/jupiter-ds';
import { useEffect, useState } from 'react';

const STORAGE_KEY = 'agent-control-time-range-preference';

export function useTimeRangePreference() {
  const [timeRangeValue, setTimeRangeValue] = useState<TimeRangeValue>(() => {
    // Initialize from localStorage or default to 1W
    if (typeof window !== 'undefined') {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          // Validate that it's a valid TimeRangeValue
          if (parsed && typeof parsed.type === 'string') {
            return parsed as TimeRangeValue;
          }
        }
      } catch (error) {
        // If parsing fails, use default
        console.warn(
          'Failed to parse time range preference from localStorage',
