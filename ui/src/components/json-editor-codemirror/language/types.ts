import type { StepSchema } from '@/core/api/types';
import type {
  JsonEditorEvaluatorOption,
  JsonEditorMode,
  JsonSchema,
} from '@/core/page-components/agent-detail/modals/edit-control/types';

export type JsonPath = Array<string | number>;

export type JsonEditorCodeMirrorContext = {
  mode: JsonEditorMode;
  schema?: JsonSchema | null;
  evaluators?: JsonEditorEvaluatorOption[];
  activeEvaluatorId?: string | null;
  steps?: StepSchema[];
};
