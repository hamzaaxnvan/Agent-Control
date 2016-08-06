import { useCallback, useMemo, useState } from 'react';

import type { ProblemDetail } from '@/core/api/types';

import type { ConfigViewMode } from './types';

export type UseEvaluatorConfigStateArgs = {
  getConfigFromForm: () => Record<string, unknown>;
  onConfigChange: (config: Record<string, unknown>) => void;
  onValidateConfig: (
    config: Record<string, unknown>,
    options?: { signal?: AbortSignal }
  ) => Promise<void>;
};

export type EvaluatorConfigState = {
  getConfigFromForm: () => Record<string, unknown>;
  configViewMode: ConfigViewMode;
  jsonText: string;
  jsonError: string | null;
  validationError: ProblemDetail | null;
  setJsonText: (value: string) => void;
  setJsonError: (error: string | null) => void;
  setValidationError: (error: ProblemDetail | null) => void;
  setConfigViewMode: (mode: ConfigViewMode) => void;
  handleConfigViewModeChange: (value: string) => Promise<void>;
  handleJsonChange: (value: string) => void;
  getJsonConfig: () => Record<string, unknown> | null;
  isJsonInvalid: boolean;
  reset: () => void;
};

export function useEvaluatorConfigState({
  getConfigFromForm,
  onConfigChange,
  onValidateConfig,
}: UseEvaluatorConfigStateArgs): EvaluatorConfigState {
  const [configViewMode, setConfigViewMode] = useState<ConfigViewMode>('form');
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<ProblemDetail | null>(
    null
  );

  const reset = useCallback(() => {
    setConfigViewMode('form');
    setJsonText('');
    setJsonError(null);
    setValidationError(null);
  }, []);

  const handleJsonChange = useCallback((value: string) => {
    setJsonText(value);
    setValidationError(null);
  }, []);

  const getJsonConfig = useCallback(() => {
    try {
      return JSON.parse(jsonText || '{}');
    } catch {
      setJsonError('Invalid JSON. Please fix before saving.');
      return null;
    }
  }, [jsonText]);

  const handleConfigViewModeChange = useCallback(
