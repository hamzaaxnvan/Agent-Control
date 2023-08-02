import { Alert, Button, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { Component, type ErrorInfo, type ReactNode } from 'react';

export type ErrorBoundaryProps = {
  children: ReactNode;
  /** Fallback UI to show on error. If not provided, uses default error UI */
  fallback?: ReactNode;
  /** Custom error handler */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Variant affects styling: 'page' for full-page, 'content' for inline, 'modal' for modals */
  variant?: 'page' | 'content' | 'modal';
};

type ErrorBoundaryState = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }
