/**
 * Form values for the SQL evaluator.
 * Uses snake_case to match API field names directly.
 */
export type SqlFormValues = {
  // Multi-Statement
  allow_multi_statements: boolean;
  max_statements: number | '';
  // Operations
  blocked_operations: string; // Comma-separated (e.g., "DROP,DELETE,TRUNCATE")
  allowed_operations: string; // Comma-separated (e.g., "SELECT,INSERT,UPDATE")
  block_ddl: boolean;
  block_dcl: boolean;
  // Table/Schema Access
