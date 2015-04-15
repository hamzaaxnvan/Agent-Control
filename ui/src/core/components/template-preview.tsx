import {
  Alert,
  Box,
  Collapse,
  Group,
  Loader,
  Text,
  Textarea,
  UnstyledButton,
} from '@mantine/core';
import { useDebouncedCallback } from '@mantine/hooks';
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import { useCallback, useEffect, useState } from 'react';

import { isApiError } from '@/core/api/errors';
import type {
  ProblemDetail,
  TemplateDefinition,
  TemplateValue,
} from '@/core/api/types';
import { useRenderTemplate } from '@/core/hooks/query-hooks/use-render-template';

type TemplatePreviewProps = {
  template: TemplateDefinition;
  values: Record<string, TemplateValue>;
  /** Called when the render endpoint returns parameter-level errors. */
  onErrors?: (errors: Record<string, string>) => void;
  debounceMs?: number;
  defaultOpen?: boolean;
};

/**
 * Calls the render preview endpoint and displays the rendered control JSON.
 */
export function TemplatePreview({
  template,
  values,
  onErrors,
  debounceMs = 600,
  defaultOpen = false,
}: TemplatePreviewProps) {
  const [opened, setOpened] = useState(defaultOpen);
  const [renderedJson, setRenderedJson] = useState('');
  const [renderError, setRenderError] = useState<ProblemDetail | null>(null);
  const renderTemplate = useRenderTemplate();

