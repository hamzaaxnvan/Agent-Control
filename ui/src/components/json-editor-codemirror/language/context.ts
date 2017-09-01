import {
  findNodeAtLocation,
  type Node as JsonNode,
  parseTree,
} from 'jsonc-parser';

import type { JsonEditorEvaluatorOption } from '@/core/page-components/agent-detail/modals/edit-control/types';

import {
  asSchema,
  getSchemaAtProperty,
  getSchemaEnumValues,
  normalizeSchema,
} from './schema';
import type {
  JsonEditorCodeMirrorContext,
  JsonPath,
  SchemaCursor,
} from './types';

export function isEvaluatorNameLocation(path: JsonPath): boolean {
  return (
    path.length >= 2 &&
    path[path.length - 1] === 'name' &&
    path[path.length - 2] === 'evaluator'
  );
}

export function isSelectorPathLocation(path: JsonPath): boolean {
  return (
    path.length >= 2 &&
    path[path.length - 1] === 'path' &&
    path[path.length - 2] === 'selector'
  );
}

export function getStringArrayAtPath(
  tree: JsonNode | undefined,
  path: JsonPath
): string[] {
  const node = tree ? findNodeAtLocation(tree, path) : undefined;
  if (!node || node.type !== 'array' || !node.children) return [];
  return node.children
    .map((child) => (typeof child.value === 'string' ? child.value : null))
    .filter((value): value is string => value !== null);
}

export function getScopeFilters(tree: JsonNode | undefined): {
  stepTypes: string[];
  stepNames: string[];
} {
  return {
    stepTypes: getStringArrayAtPath(tree, ['scope', 'step_types']),
    stepNames: getStringArrayAtPath(tree, ['scope', 'step_names']),
  };
}

export function resolveActiveEvaluator(
  context: JsonEditorCodeMirrorContext,
  tree: JsonNode | undefined,
  path: JsonPath
): JsonEditorEvaluatorOption | null {
  if (context.mode === 'evaluator-config') {
    return (
      context.evaluators?.find(
        (item) => item.id === context.activeEvaluatorId
      ) ?? null
    );
  }

  const evaluatorIndex = path.lastIndexOf('evaluator');
  if (evaluatorIndex === -1 || !tree) return null;
  const evaluatorPath = path.slice(0, evaluatorIndex + 1);
  const nameNode = findNodeAtLocation(tree, [...evaluatorPath, 'name']);
  const value = typeof nameNode?.value === 'string' ? nameNode.value : null;
