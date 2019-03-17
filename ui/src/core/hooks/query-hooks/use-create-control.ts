import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { ControlDefinition } from '@/core/api/types';

type CreateControlParams = {
  name: string;
  definition: ControlDefinition;
};

/**
 * Mutation hook to create a new control with its definition in one request.
 */
export function useCreateControl() {
  const queryClient = useQueryClient();

