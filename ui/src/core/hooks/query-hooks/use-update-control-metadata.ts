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
