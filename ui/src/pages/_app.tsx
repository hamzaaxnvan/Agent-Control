// Import Mantine styles
import '@mantine/core/styles.css';
import '@mantine/dates/styles.css';
import '@mantine/charts/styles.css';
import '@mantine/code-highlight/styles.css';
import '@mantine/notifications/styles.css';
// Import jupiter-ds styles
import '@rungalileo/jupiter-ds/styles.css';
// Import rungalileo icons styles
import '@rungalileo/icons/styles.css';
// Import global styles
import '@/styles/globals.css';

import { MantineProvider } from '@mantine/core';
import { DatesProvider } from '@mantine/dates';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { JupiterThemeProvider } from '@rungalileo/jupiter-ds';
import type { AppProps } from 'next/app';
import Head from 'next/head';

import { ErrorBoundary } from '@/components/error-boundary';
import { LoginModal } from '@/core/components/login-modal';
import { AuthProvider, useAuth } from '@/core/providers/auth-provider';
import { QueryProvider } from '@/core/providers/query-provider';
import type { NextPageWithLayout } from '@/core/types/page';
import { appTheme } from '@/theme';

type AppPropsWithLayout = AppProps & {
  Component: NextPageWithLayout;
};

// Custom theme override to use Inter and Fira Mono fonts

function AuthGate({ children }: { children: React.ReactNode }) {
  const { auth } = useAuth();

  if (auth.status === 'loading') {
    // Avoid rendering the main UI until we know whether auth is required.
    return null;
  }

  if (auth.status === 'error') {
    return (
      <div style={{ padding: 24 }}>
        <p style={{ fontWeight: 500 }}>
          Unable to connect to Agent Control server.
        </p>
        <p style={{ fontSize: 12, color: 'var(--mantine-color-dimmed)' }}>
