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

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Log error to console (can be extended to send to monitoring service)
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  handleRefresh = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // Custom fallback
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback based on variant
      const { variant = 'content' } = this.props;

      if (variant === 'page') {
        return <FullPageError onRefresh={this.handleRefresh} />;
      }

      if (variant === 'modal') {
        return <ModalError onRetry={this.handleReset} />;
      }

      // Default: content variant
      return <ContentError onRetry={this.handleReset} />;
    }

    return this.props.children;
  }
}

// Full page error - used at top level
function FullPageError({ onRefresh }: { onRefresh: () => void }) {
  return (
    <Stack
      align="center"
      justify="center"
      h="100vh"
      gap="lg"
      p="xl"
      bg="var(--mantine-color-body)"
      style={{ textAlign: 'center' }}
    >
      <IconAlertTriangle size={64} color="var(--mantine-color-red-6)" />
      <Title order={2}>Something went wrong</Title>
      <Text c="dimmed" maw={400}>
        An unexpected error occurred. Please refresh the page to try again.
      </Text>
      <Button onClick={onRefresh} variant="filled">
        Refresh page
      </Button>
    </Stack>
  );
}

// Content area error - used inside layout, keeps nav visible
function ContentError({ onRetry }: { onRetry: () => void }) {
  return (
    <Stack align="center" justify="center" h="100vh" p="xl">
      <Alert
        icon={<IconAlertTriangle size={20} />}
        title="Something went wrong"
        color="red"
        variant="light"
        maw={500}
      >
        <Stack gap="sm">
