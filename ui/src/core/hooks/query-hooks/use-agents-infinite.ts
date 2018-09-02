import { useInfiniteQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { ListAgentsResponse } from '@/core/api/types';

const AGENTS_PAGE_SIZE = 10;

export type UseAgentsInfiniteParams = {
  name?: string;
