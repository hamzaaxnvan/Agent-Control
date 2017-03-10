import type { UseQueryOptions, UseQueryResult } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { GetAgentPathParams, GetAgentResponse } from '@/core/api/types';

/**
 * Query hook to fetch a single agent by ID
 *
 * @param agentId - UUID of the agent (required)
 *
 */
export function useAgent(
  agentId: GetAgentPathParams['agent_name'],
  options?: Omit<
    UseQueryOptions<
      GetAgentResponse,
      Error,
      GetAgentResponse,
