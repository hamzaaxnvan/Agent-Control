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
