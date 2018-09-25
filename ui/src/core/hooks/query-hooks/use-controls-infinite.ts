import { useInfiniteQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { ListControlsResponse } from '@/core/api/types';

const CONTROLS_PAGE_SIZE = 10;

export type UseControlsInfiniteParams = {
  name?: string;
  enabled?: boolean;
  step_type?: string;
  stage?: string;
  execution?: string;
  tag?: string;
};

/**
 * Infinite query hook to fetch controls with cursor-based pagination
 * Supports server-side filtering by name and other params
 */
export function useControlsInfinite(params?: UseControlsInfiniteParams) {
  const { enabled = true, ...filterParams } = params ?? {};

