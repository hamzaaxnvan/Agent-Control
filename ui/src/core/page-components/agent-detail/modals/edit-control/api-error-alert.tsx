import { Alert, List, Text } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';

import type { ProblemDetail } from '@/core/api/types';

/** Convert API field path (e.g. data.evaluator.match_on) to user-friendly label (e.g. Match on) */
function formatFieldForDisplay(apiField: string | null): string {
  if (!apiField) return '';
  const lastSegment = apiField.split('.').pop() ?? apiField;
  return lastSegment
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

