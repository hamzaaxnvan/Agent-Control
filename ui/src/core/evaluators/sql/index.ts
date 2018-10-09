import type { EvaluatorDefinition } from '../types';
import { SqlForm } from './form';
import type { SqlFormValues } from './types';

/** Helper to split comma-separated string into array */
const splitList = (value: string, uppercase = false): string[] => {
  const items = value
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s !== '');
  return uppercase ? items.map((s) => s.toUpperCase()) : items;
};

/** Helper to return array or null if empty */
const arrayOrNull = (arr: string[]): string[] | null =>
  arr.length > 0 ? arr : null;

/** Helper to return number or null */
const numberOrNull = (value: number | ''): number | null =>
  value === '' ? null : value;

/**
 * SQL evaluator definition.
 *
 * Validates SQL queries for operations, table access, column presence, and complexity.
 */
export const sqlEvaluator: EvaluatorDefinition<SqlFormValues> = {
  id: 'sql',
  displayName: 'SQL',

  initialValues: {
    allow_multi_statements: true,
    max_statements: '',
    blocked_operations: '',
    allowed_operations: '',
    block_ddl: false,
    block_dcl: false,
    allowed_tables: '',
    blocked_tables: '',
    allowed_schemas: '',
    blocked_schemas: '',
    required_columns: '',
    column_presence_logic: 'any',
    column_context: '',
    column_context_scope: 'all',
    require_limit: false,
    max_limit: '',
    max_result_window: '',
    case_sensitive: false,
    dialect: 'postgres',
    max_subquery_depth: '',
    max_joins: '',
    max_union_count: '',
  },

  validate: {
    max_statements: (value, values) => {
      if (value !== '' && !values.allow_multi_statements) {
        return 'Max statements can only be set when multi-statements are allowed';
      }
      return null;
    },
    blocked_operations: (value, values) => {
      if (value && values.allowed_operations) {
        return 'Cannot use both blocked and allowed operations';
      }
      return null;
    },
    allowed_operations: (value, values) => {
      if (value && values.blocked_operations) {
        return 'Cannot use both blocked and allowed operations';
      }
      return null;
    },
    allowed_tables: (value, values) => {
      if (value && values.blocked_tables) {
        return 'Cannot use both allowed and blocked tables';
      }
      return null;
    },
    blocked_tables: (value, values) => {
      if (value && values.allowed_tables) {
        return 'Cannot use both allowed and blocked tables';
      }
      return null;
    },
    allowed_schemas: (value, values) => {
      if (value && values.blocked_schemas) {
        return 'Cannot use both allowed and blocked schemas';
      }
      return null;
    },
    blocked_schemas: (value, values) => {
      if (value && values.allowed_schemas) {
        return 'Cannot use both allowed and blocked schemas';
      }
      return null;
    },
  },

  toConfig: (values) => ({
    // Multi-Statement
    allow_multi_statements: values.allow_multi_statements,
    max_statements: numberOrNull(values.max_statements),
    // Operations - convert comma-separated strings to arrays
    blocked_operations: arrayOrNull(splitList(values.blocked_operations, true)),
    allowed_operations: arrayOrNull(splitList(values.allowed_operations, true)),
    block_ddl: values.block_ddl,
    block_dcl: values.block_dcl,
    // Table/Schema Access
    allowed_tables: arrayOrNull(splitList(values.allowed_tables)),
    blocked_tables: arrayOrNull(splitList(values.blocked_tables)),
    allowed_schemas: arrayOrNull(splitList(values.allowed_schemas)),
    blocked_schemas: arrayOrNull(splitList(values.blocked_schemas)),
