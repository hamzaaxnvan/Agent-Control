import { useMutation } from '@tanstack/react-query';

import { api } from '@/core/api/client';
import { parseApiError } from '@/core/api/errors';
import type { RenderControlTemplateRequest } from '@/core/api/types';

