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
