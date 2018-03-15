export type ControlAction = "deny" | "steer" | "observe";

export interface EvaluationResult {
  isSafe: boolean;
  reason?: string;
}

export class ControlViolationError extends Error {
  readonly controlName: string;
  readonly controlId: string;
  readonly action: ControlAction;
  readonly evaluationResult: EvaluationResult;

  constructor(params: {
