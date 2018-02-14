import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import { parseApiError } from '@/core/api/errors';

type RemoveControlFromAgentParams = {
  agentId: string;
  controlId: number;
};

export type RemoveControlFromAgentResult = {
  success: boolean;
  removed_direct_association: boolean;
  control_still_active: boolean;
