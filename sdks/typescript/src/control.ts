export interface ControlOptions {
  policy?: string;
}

export type AsyncFn<TArgs extends unknown[], TResult> = (...args: TArgs) => Promise<TResult>;

