/**
 * Utilities for mapping API errors to form fields.
 *
 * Since form fields use snake_case to match API field names directly,
 * the mapping logic is simple - just extract the field name from the path.
 */

import type { UseFormReturnType } from '@mantine/form';

import type { ValidationErrorItem } from '@/core/api/types';

/**
 * Mapping result indicating which form and field an API error belongs to
 */
type FieldMapping = {
  form: 'definition' | 'evaluator';
  field: string;
};

/**
 * Map an API error field path to a form field.
 *
 * API field paths look like:
 * - "name" (control name)
 * - "data.scope.step_types" (definition field)
 * - "data.condition.selector.path" → selector_path (definition field)
 * - "data.condition.evaluator.config.pattern" (evaluator config field)
 *
 * Since forms use snake_case, we can directly use the API field names.
 *
 * @param apiField The field path from the API error
 * @returns The form and field name, or null if unmapped
 */
export function mapApiFieldToFormField(
  apiField: string | null
): FieldMapping | null {
  if (!apiField) return null;

  // Handle "name" directly (control name)
  if (apiField === 'name') {
    return { form: 'definition', field: 'name' };
  }

  // Handle "data." prefix
  const dataPrefix = 'data.';
  if (!apiField.startsWith(dataPrefix)) {
    return null;
  }

  const fieldPath = apiField.slice(dataPrefix.length);

  const leafConditionPrefix = 'condition.';
