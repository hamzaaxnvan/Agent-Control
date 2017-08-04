import { useInfiniteQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { ListAgentsResponse } from '@/core/api/types';

const AGENTS_PAGE_SIZE = 10;

export type UseAgentsInfiniteParams = {
  name?: string;
  enabled?: boolean;
};

/**
 * Infinite query hook to fetch agents with cursor-based pagination
 * Supports server-side filtering by name
 */
export function useAgentsInfinite(params?: UseAgentsInfiniteParams) {
  const { enabled = true, ...filterParams } = params ?? {};

