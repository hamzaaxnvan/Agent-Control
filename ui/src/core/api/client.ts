import createClient from 'openapi-fetch';

import type { paths } from './generated/api-types';
import type {
  CreateControlRequest,
  GetAgentControlsPathParams,
  GetAgentPathParams,
  GetControlSchemaResponse,
  InitAgentRequestBody,
  ListAgentsQueryParams,
  PatchControlRequest,
  RenderControlTemplateRequest,
  RenderControlTemplateResponse,
  SetControlDataRequest,
  ValidateControlDataRequest,
  ValidateControlDataResponse,
} from './types';

const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
const isStaticExport = process.env.NEXT_PUBLIC_STATIC_EXPORT === 'true';
const API_URL =
  configuredApiUrl ?? (isStaticExport ? '' : 'http://localhost:8000');

export const apiClient = createClient<paths>({
  baseUrl: API_URL,
  credentials: 'include',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Global 401 listener — UI components can subscribe to be notified when
// a request is rejected due to missing/expired credentials.
type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

apiClient.use({
  async onResponse({ response }) {
    if (response.status === 401) {
      unauthorizedListeners.forEach((fn) => fn());
    }
    return response;
  },
});

// ------------------------------------------------------------------
// Auth API (not part of the generated OpenAPI types)
// ------------------------------------------------------------------

export type ServerConfig = {
  requires_api_key: boolean;
  auth_mode: 'none' | 'api-key';
  has_active_session: boolean;
};

export type LoginResponse = {
  authenticated: boolean;
  is_admin: boolean;
};

const authBaseUrl = API_URL || '';

export const authApi = {
  getConfig: async (): Promise<ServerConfig> => {
    const res = await fetch(`${authBaseUrl}/api/config`, {
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Failed to fetch server config');
    return res.json() as Promise<ServerConfig>;
  },

  login: async (
    apiKey: string
  ): Promise<{ status: number; data: LoginResponse }> => {
    const res = await fetch(`${authBaseUrl}/api/login`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    const data = (await res.json()) as LoginResponse;
    return { status: res.status, data };
  },
