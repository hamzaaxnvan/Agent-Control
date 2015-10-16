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

export type ApiErrorAlertProps = {
  /** The API error to display */
  error: ProblemDetail | null;
  /** Unmapped field errors to show in the list */
  unmappedErrors?: Array<{ field: string | null; message: string }>;
  /** Callback when the alert is dismissed */
  onClose?: () => void;
};

/**
 * Alert component for displaying API errors with field-level details.
 * Renders error.errors from the API when available, or unmappedErrors from form mapping.
 */
export const ApiErrorAlert = ({
  error,
  unmappedErrors = [],
  onClose,
}: ApiErrorAlertProps) => {
  if (!error) return null;

  const errorsToShow =
    unmappedErrors.length > 0
      ? unmappedErrors
      : (error.errors ?? []).map((e) => ({
          field: e.field,
          message: e.message,
        }));

  return (
    <Alert
