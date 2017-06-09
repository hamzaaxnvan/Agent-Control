/**
 * Form values for the JSON evaluator.
 * Uses snake_case to match API field names directly.
 */
export type JsonFormValues = {
  /** JSON Schema specification (Draft 7 or later) */
  json_schema: string;
  /** Comma-separated list of required fields (dot notation) */
  required_fields: string;
  /** JSON mapping of field paths to expected types */
  field_types: string;
  /** JSON mapping of field paths to constraints */
  field_constraints: string;
