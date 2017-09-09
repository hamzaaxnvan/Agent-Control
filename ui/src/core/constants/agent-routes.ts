export type AgentDetailTab = 'controls' | 'monitor';

type RouteQueryValue =
  | string
  | number
  | boolean
  | readonly string[]
  | string[]
  | null
  | undefined;

type AgentRouteOptions = {
  tab?: AgentDetailTab;
  query?: Record<string, RouteQueryValue>;
};

export function getAgentRoute(
  agentId: string,
  options?: AgentRouteOptions
): string {
  const params = new URLSearchParams();
  params.set('id', agentId);

