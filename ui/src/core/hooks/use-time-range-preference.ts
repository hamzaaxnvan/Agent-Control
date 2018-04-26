import type { TimeRangeValue } from '@rungalileo/jupiter-ds';
import { useEffect, useState } from 'react';

const STORAGE_KEY = 'agent-control-time-range-preference';

export function useTimeRangePreference() {
  const [timeRangeValue, setTimeRangeValue] = useState<TimeRangeValue>(() => {
    // Initialize from localStorage or default to 1W
    if (typeof window !== 'undefined') {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
