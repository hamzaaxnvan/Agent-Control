export type ControlAction = "deny" | "steer" | "observe";

export interface EvaluationResult {
  isSafe: boolean;
  reason?: string;
}

