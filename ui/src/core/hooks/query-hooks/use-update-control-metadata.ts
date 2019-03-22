import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import { parseApiError } from '@/core/api/errors';
import type { PatchControlRequest } from '@/core/api/types';

type UpdateControlMetadataParams = {
  agentId: string;
  controlId: number;
  data: PatchControlRequest;
};

/**
 * Mutation hook to update control metadata (name, enabled status).
 *
 * This wraps the PATCH /api/v1/controls/{control_id} endpoint.
 */
export function useUpdateControlMetadata() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ controlId, data }: UpdateControlMetadataParams) => {
      const {
        data: result,
        error,
        response,
      } = await api.controls.updateMetadata(controlId, data);

      if (error) {
        throw parseApiError(
          error,
          'Failed to update control metadata',
          response?.status
