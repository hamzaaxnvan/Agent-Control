/**
 * Re-export commonly used types from the generated API types
 * This makes it easier to import types without the verbose path
 */
import type { components, operations } from './generated/api-types';

// =============================================================================
// Error Types (RFC 7807 ProblemDetail)
// =============================================================================

/**
 * Validation error item (GitHub-style field-level error)
 */
export type ValidationErrorItem = {
  /** Resource type where error occurred (e.g., 'Control') */
  resource: string;
  /** Field path that caused the error (e.g., 'data.evaluator.config.pattern') */
  field: string | null;
  /** Machine-readable error code (e.g., 'required', 'invalid_format') */
  code: string;
  /** Human-readable error message */
  message: string;
  /** The invalid value (omitted for sensitive data) */
  value?: unknown;
};

/**
 * RFC 7807 Problem Detail error response
 */
export type ProblemDetail = {
  /** Error type URI */
  type: string;
  /** Short error title */
  title: string;
  /** HTTP status code */
  status: number;
  /** Human-readable error detail */
  detail: string;
  /** Request path */
  instance?: string;
  /** Machine-readable error code */
  error_code: string;
  /** Kubernetes-style reason */
  reason: string;
  /** Array of field-level validation errors */
  errors?: ValidationErrorItem[];
  /** Actionable hint for resolution */
  hint?: string;
};

// Agent types
export type Agent = components['schemas']['Agent'];
export type EvaluatorSchema = components['schemas']['EvaluatorSchema'];
export type StepSchema = components['schemas']['StepSchema'];
