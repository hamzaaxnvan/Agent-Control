export const DEFENSECLAW_SEVERITIES = [
  'LOW',
  'MEDIUM',
  'HIGH',
  'CRITICAL',
] as const;

export type DefenseClawSeverity = (typeof DEFENSECLAW_SEVERITIES)[number];

export type DefenseClawRuleFormValue = {
  id: string;
  pattern: string;
  title: string;
  severity: DefenseClawSeverity;
