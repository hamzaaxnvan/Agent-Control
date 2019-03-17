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

      try {
        // Step 1: Create and validate the control atomically.
        const {
          data: createControlResult,
          error: createControlError,
          response: createControlResponse,
        } = await api.controls.create({ name: controlName, data: definition });

        if (createControlError || !createControlResult) {
          throw parseApiError(
            createControlError,
            'Failed to create control',
            createControlResponse?.status
          );
        }

        createdControlId = createControlResult.control_id;

        // Step 2: Associate control directly with the agent.
        const { error: associateError, response: associateResponse } =
          await api.agents.addControl(agentId, createdControlId);

        if (associateError) {
          throw parseApiError(
            associateError,
            'Failed to add control to agent',
            associateResponse?.status
          );
        }
