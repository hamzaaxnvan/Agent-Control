'use client';

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';

import {
  authApi,
  type LoginResponse,
  onUnauthorized,
  type ServerConfig,
} from '@/core/api/client';

type AuthState =
  | { status: 'loading' }
  | { status: 'not-required' }
  | { status: 'needs-login' }
  | { status: 'authenticated'; isAdmin: boolean }
  | { status: 'error'; message: string };

type AuthContextValue = {
  auth: AuthState;
  login: (apiKey: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}

type AuthProviderProps = { children: ReactNode };

export function AuthProvider({ children }: AuthProviderProps) {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' });

  // Fetch server config on mount to decide if auth is required
  useEffect(() => {
    let cancelled = false;

    authApi
      .getConfig()
      .then((config: ServerConfig) => {
        if (cancelled) return;
        if (!config.requires_api_key) {
          setAuth({ status: 'not-required' });
        } else {
          if (config.has_active_session) {
            // Cookie or header already authenticated; no need to prompt.
            setAuth({ status: 'authenticated', isAdmin: false });
          } else {
            setAuth({ status: 'needs-login' });
          }
        }
      })
      .catch(() => {
        if (cancelled) return;
        // If config fetch fails, surface an explicit error so the UI
        // can show a proper message instead of silently disabling auth.
        setAuth({
          status: 'error',
          message:
            'Unable to reach Agent Control server. Check that it is running.',
        });
      });
