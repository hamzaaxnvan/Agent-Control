/**
 * Form values for the list evaluator.
 * Uses snake_case to match API field names directly.
 */
export type ListFormValues = {
  /** Newline-separated list of values */
  values: string;
  /** Match logic: any or all */
  logic: 'any' | 'all';
