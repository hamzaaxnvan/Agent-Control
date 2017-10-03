import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import { parseApiError } from '@/core/api/errors';
import type { ControlDefinition } from '@/core/api/types';

type UpdateControlParams = {
  agentId: string;
  controlId: number;
  definition: ControlDefinition;
};

/**
 * Mutation hook to update an existing control's definition
 */
