/**
 * Luna comparison operator types.
 *
 * Numeric operators (gt, gte, lt, lte) require a numeric threshold.
 */
export type LunaOperator =
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'eq'
  | 'ne'
  | 'contains'
  | 'any';

/**
 * Which scorer input side to evaluate for scalar selected data.
 */
export type LunaPayloadField = 'input' | 'output';
