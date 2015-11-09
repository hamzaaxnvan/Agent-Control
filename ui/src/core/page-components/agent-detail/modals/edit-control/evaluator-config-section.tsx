import {
  Anchor,
  Group,
  Paper,
  ScrollArea,
  SegmentedControl,
  Stack,
  Text,
} from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { IconExternalLink } from '@tabler/icons-react';
import { useState } from 'react';

import type { ProblemDetail } from '@/core/api/types';

import { JsonEditorView } from './json-editor-view';
import type { ConfigViewMode } from './types';
import type { JsonSchema } from './types';

const DEFAULT_HEIGHT = 450;
const CONTENT_MIN_HEIGHT_EXTRA = 60;
type ValidationStatus = 'idle' | 'validating' | 'valid' | 'invalid';

type EvaluatorConfigSectionProps = {
  config: {
    configViewMode: ConfigViewMode;
    jsonText: string;
    jsonError: string | null;
    validationError: ProblemDetail | null;
    handleConfigViewModeChange: (value: string) => Promise<void>;
    handleJsonChange: (value: string) => void;
    setJsonError: (error: string | null) => void;
    setValidationError: (error: ProblemDetail | null) => void;
  };
  onValidateConfig: (
    config: Record<string, unknown>,
    options?: { signal?: AbortSignal }
  ) => Promise<void>;
  onConfigChange: (config: Record<string, unknown>) => void;
  evaluatorForm: UseFormReturnType<any>;
  formComponent?: React.ComponentType<{ form: UseFormReturnType<any> }>;
  height?: number;
  activeEvaluatorId?: string;
  activeEvaluatorSchema?: JsonSchema | null;
};

export function EvaluatorConfigSection({
  config,
  onValidateConfig,
