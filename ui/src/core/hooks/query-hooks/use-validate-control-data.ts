import { useMutation } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import { parseApiError } from '@/core/api/errors';
import type { ControlDefinition } from '@/core/api/types';

export type ValidateControlDataVariables = {
  definition: ControlDefinition;
  signal?: AbortSignal;
};

/**
