import { useQuery } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import type { EvaluatorsResponse } from '@/core/api/types';

/**
 * Query hook to fetch available evaluators.
