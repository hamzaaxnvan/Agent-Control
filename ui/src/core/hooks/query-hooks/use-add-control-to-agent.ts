import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import { parseApiError } from '@/core/api/errors';
import type { ControlDefinition } from '@/core/api/types';

type AddControlToAgentParams = {
  agentId: string;
  controlName: string;
  definition: ControlDefinition;
};

/**
 * Mutation hook to add a control to an agent
 * Flow:
 * 1. Create the control with its definition
 * 2. Associate the control directly with the agent
 */
export function useAddControlToAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      agentId,
      controlName,
      definition,
    }: AddControlToAgentParams) => {
      let createdControlId: number | null = null;

