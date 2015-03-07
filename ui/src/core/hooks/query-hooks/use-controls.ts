import { useQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';

export type UseControlsParams = {
  cursor?: number;
  limit?: number;
  name?: string;
  enabled?: boolean;
  step_type?: string;
