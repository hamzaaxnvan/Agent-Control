import {
  findNodeAtLocation,
  type Node as JsonNode,
  parseTree,
} from 'jsonc-parser';

import type {
  JsonEditorEvaluatorOption,
  JsonEditorMode,
} from '@/core/page-components/agent-detail/modals/edit-control/types';

import {
  asSchema,
  getSchemaDefault,
  getSchemaEnumValues,
  getSchemaProperties,
  getSchemaRequiredProperties,
  getSchemaType,
  normalizeSchema,
} from './schema';
import type { JsonEditorTextEdit } from './types';

type EvaluatorNodeInfo = {
  name: string;
  nameNode: JsonNode;
  configNode: JsonNode | undefined;
};

function collectEvaluatorNames(
  node: JsonNode | undefined,
  result: Map<string, EvaluatorNodeInfo>
) {
  if (!node || node.type !== 'object' || !node.children) return;

  const evaluatorNode = findNodeAtLocation(node, ['evaluator']);
  if (evaluatorNode?.type === 'object') {
    const nameNode = findNodeAtLocation(evaluatorNode, ['name']);
    const configNode = findNodeAtLocation(evaluatorNode, ['config']);
    if (nameNode && typeof nameNode.value === 'string') {
      result.set(`${nameNode.offset}`, {
        name: nameNode.value,
        nameNode,
        configNode,
      });
    }
  }

  for (const key of ['and', 'or'] as const) {
    const arrayNode = findNodeAtLocation(node, [key]);
    if (arrayNode?.type === 'array' && arrayNode.children) {
      for (const child of arrayNode.children)
        collectEvaluatorNames(child, result);
    }
  }

  const notNode = findNodeAtLocation(node, ['not']);
  if (notNode?.type === 'object') collectEvaluatorNames(notNode, result);
}

export function extractEvaluatorNames(text: string): Map<string, string> {
  const tree = parseTree(text);
  if (!tree) return new Map();
  const conditionNode = findNodeAtLocation(tree, ['condition']);
  const result = new Map<string, EvaluatorNodeInfo>();
  collectEvaluatorNames(conditionNode, result);
  const names = new Map<string, string>();
  for (const [key, info] of result) names.set(key, info.name);
  return names;
}

function getDefaultValueForSchema(
  propSchema: Record<string, unknown>
): unknown {
  const defaultValue = getSchemaDefault(propSchema);
  if (defaultValue !== undefined) return defaultValue;
  const enumValues = getSchemaEnumValues(propSchema);
  if (enumValues.length > 0) return enumValues[0];
  switch (getSchemaType(propSchema)) {
    case 'string':
      return '';
    case 'number':
    case 'integer':
      return 0;
    case 'boolean':
      return false;
    case 'array':
      return [];
    case 'object':
      return {};
    default:
      return null;
  }
}

function buildDefaultConfig(configSchema: unknown): Record<string, unknown> {
  const schema = asSchema(configSchema);
  if (!schema) return {};
  const normalized = normalizeSchema(schema, schema);
  if (!normalized) return {};
  const properties = getSchemaProperties(normalized);
  const required = new Set(getSchemaRequiredProperties(normalized));
  const config: Record<string, unknown> = {};
  for (const [name, raw] of Object.entries(properties)) {
    const propSchema = normalizeSchema(raw, schema);
    if (!propSchema) continue;
    const explicitDefault = getSchemaDefault(propSchema);
    if (required.has(name) || explicitDefault !== undefined) {
      config[name] = getDefaultValueForSchema(propSchema);
    }
  }
  return config;
}

function findEvaluatorConfigEdit(
  text: string,
  previousNames: Map<string, string>,
  evaluators: JsonEditorEvaluatorOption[] | undefined
): JsonEditorTextEdit | null {
  const tree = parseTree(text);
  if (!tree) return null;
  const conditionNode = findNodeAtLocation(tree, ['condition']);
  const result = new Map<string, EvaluatorNodeInfo>();
  collectEvaluatorNames(conditionNode, result);

  for (const [key, { name, configNode, nameNode }] of result) {
    const prevName = previousNames.get(key);
    if (prevName === undefined || prevName === name) continue;
    const evaluator = evaluators?.find((item) => item.id === name);
    if (!evaluator) continue;
