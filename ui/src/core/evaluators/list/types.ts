/**
 * Form values for the list evaluator.
 * Uses snake_case to match API field names directly.
 */
export type ListFormValues = {
  /** Newline-separated list of values */
  values: string;
  /** Match logic: any or all */
  logic: 'any' | 'all';
  /** When to trigger: on match or no match */
  match_on: 'match' | 'no_match';
  /** Match mode: exact, contains, starts_with, or ends_with */
