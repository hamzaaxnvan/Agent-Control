export interface ControlOptions {
  policy?: string;
}

export type AsyncFn<TArgs extends unknown[], TResult> = (...args: TArgs) => Promise<TResult>;

/**
 * Minimal no-op control wrapper scaffold.
 * Evaluation integration lands in a later phase.
 */
