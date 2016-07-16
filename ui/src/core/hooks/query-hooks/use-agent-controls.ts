import { useQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type {
  AgentControlsResponse,
  GetAgentControlsPathParams,
} from '@/core/api/types';

/**
 * Query hook to fetch active controls for an agent
 *
 * @param agentId - UUID of the agent (required)
