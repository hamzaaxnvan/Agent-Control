import { AgentControlSDK } from "./generated/sdk/sdk";
import type { Logger } from "./generated/lib/logger";

export interface StepSchema {
  name: string;
  schema: Record<string, unknown>;
}

export type APIKeyProvider = string | (() => Promise<string>);

export interface AgentControlInitOptions {
  agentName: string;
  agentId?: string;
  serverUrl: string;
  apiKey?: APIKeyProvider;
  steps?: StepSchema[];
  timeoutMs?: number;
  userAgent?: string;
  debugLogger?: Logger;
}

export type AgentsApi = AgentControlSDK["agents"];
export type AuthApi = AgentControlSDK["auth"];
export type ControlBindingsApi = AgentControlSDK["controlBindings"];
export type ControlsApi = AgentControlSDK["controls"];
export type EvaluationApi = AgentControlSDK["evaluation"];
export type EvaluatorsApi = AgentControlSDK["evaluators"];
export type ObservabilityApi = AgentControlSDK["observability"];
export type PoliciesApi = AgentControlSDK["policies"];
export type SystemApi = AgentControlSDK["system"];

export class AgentControlClient {
  private options: AgentControlInitOptions | null = null;
  private sdk: AgentControlSDK | null = null;

  init(options: AgentControlInitOptions): void {
    this.options = { ...options };
    this.sdk = new AgentControlSDK({
      serverURL: options.serverUrl,
      apiKeyHeader: options.apiKey,
      timeoutMs: options.timeoutMs,
      userAgent: options.userAgent,
      debugLogger: options.debugLogger,
    });
  }

  get initialized(): boolean {
    return this.sdk !== null;
  }

