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
