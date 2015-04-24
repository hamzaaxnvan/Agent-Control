import type { EvaluatorDefinition } from '../types';
import { DefenseClawOpaPolicyForm } from './opa-policy-form';
import {
  createBlankDefenseClawRule,
  DefenseClawRulePackForm,
} from './rule-pack-form';
import {
  DEFENSECLAW_SEVERITIES,
  type DefenseClawOpaPolicyFormValues,
  type DefenseClawRuleFormValue,
  type DefenseClawRulePackFormValues,
} from './types';

const severityValues = new Set<string>(DEFENSECLAW_SEVERITIES);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const normalizeRule = (value: unknown): DefenseClawRuleFormValue => {
  if (!isRecord(value)) return createBlankDefenseClawRule();
  return {
    id: typeof value.id === 'string' ? value.id : '',
    pattern: typeof value.pattern === 'string' ? value.pattern : '',
    title: typeof value.title === 'string' ? value.title : '',
    severity: severityValues.has(String(value.severity))
      ? (value.severity as DefenseClawRuleFormValue['severity'])
      : 'HIGH',
    confidence: typeof value.confidence === 'number' ? value.confidence : 0.99,
