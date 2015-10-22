/**
 * API error utilities for handling RFC 7807 ProblemDetail responses
 */

import type { ProblemDetail } from './types';

/**
 * Custom error class that includes the ProblemDetail response
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public problemDetail: ProblemDetail
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Create a fallback ProblemDetail for unexpected errors
 */
export function createFallbackProblemDetail(
  message: string,
  status = 500
): ProblemDetail {
  return {
    type: 'about:blank',
    title: 'Error',
    status,
    detail: message,
    error_code: 'UNKNOWN_ERROR',
    reason: 'Unknown',
  };
}

/**
 * Parse an error response into an ApiError
 * Handles both ProblemDetail responses and generic errors
 */
export function parseApiError(
  error: unknown,
