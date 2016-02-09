import {
  findNodeAtLocation,
  findNodeAtOffset,
  getLocation,
  type Node as JsonNode,
  type ParseError,
  parseTree,
} from 'jsonc-parser';

import { removeTrailingCommasOutsideStrings } from '@/components/json-editor-shared/fix-json-commas';
import type { StepSchema } from '@/core/api/types';
import type {
  JsonEditorEvaluatorOption,
  JsonEditorMode,
  JsonSchema,
} from '@/core/page-components/agent-detail/modals/edit-control/types';

type MonacoModule = typeof import('monaco-editor');
type JsonPath = Array<string | number>;

type JsonEditorAutocompleteContext = {
  mode: JsonEditorMode;
  modelUri: string;
  schema?: JsonSchema | null;
  evaluators?: JsonEditorEvaluatorOption[];
  activeEvaluatorId?: string | null;
  steps?: StepSchema[];
  /** For template mode: path prefix under which the ControlDefinition lives */
  definitionPrefix?: JsonPath;
  /** For template mode: parameter names for $param completions */
  templateParameterNames?: string[];
};

type SelectorPathSuggestion = {
  label: string;
  detail: string;
  rank: number;
};

type SchemaCursor = {
  schema: JsonSchema | null;
  rootSchema: JsonSchema | null;
};

type SnippetState = {
  nextTabStop: number;
};

const ROOT_SELECTOR_PATHS = ['*', 'input', 'output', 'context', 'name', 'type'];
const COMPLETION_TRIGGER_CHARACTERS = ['"', ':', '.', ',', '['];
const SCHEMA_COMPOSITION_KEYS = ['$ref', 'allOf', 'anyOf', 'oneOf'];
const RESERVED_SCHEMA_KEYS = new Set([
  ...SCHEMA_COMPOSITION_KEYS,
  '$defs',
  'additionalProperties',
  'default',
  'description',
  'enum',
  'examples',
  'items',
  'properties',
  'required',
  'title',
  'type',
]);

// ---------------------------------------------------------------------------
// Template mode: path-prefix helpers
// ---------------------------------------------------------------------------

export const TEMPLATE_DEFINITION_PREFIX: JsonPath = [
  'template',
  'definition_template',
];

/**
 * Strip the definition prefix from a full JSON path.
 * Returns the relative path inside the definition, or null if the path is
 * not inside the definition subtree.
 */
function stripDefinitionPrefix(
  path: JsonPath,
  prefix: JsonPath | undefined
): JsonPath | null {
  if (!prefix || prefix.length === 0) return path;
  if (path.length < prefix.length) return null;
  for (let i = 0; i < prefix.length; i++) {
    if (path[i] !== prefix[i]) return null;
  }
  return path.slice(prefix.length);
}

/**
 * Navigate to the definition subtree within a parsed JSON tree.
 */
function getDefinitionSubtree(
  tree: JsonNode | undefined,
  prefix: JsonPath | undefined
): JsonNode | undefined {
  if (!tree || !prefix || prefix.length === 0) return tree;
  return findNodeAtLocation(tree, prefix) ?? undefined;
}

/**
 * Check whether a path is inside the template_values object.
 */
function isInsideTemplateValues(path: JsonPath): boolean {
  return path.length >= 1 && path[0] === 'template_values';
}

/**
 * Detect cursor at a $param string value: {"$param": "<cursor>"}
 */
function isParamRefValueLocation(path: JsonPath): boolean {
  return path.length >= 1 && path[path.length - 1] === '$param';
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asSchema(schema: unknown): JsonSchema | null {
  return isObject(schema) ? schema : null;
}

function getStringArrayAtPath(
  tree: JsonNode | undefined,
  path: JsonPath
): string[] {
  const node = tree ? findNodeAtLocation(tree, path) : undefined;
  if (!node || node.type !== 'array' || !node.children) {
    return [];
  }

  return node.children
    .map((child) => (typeof child.value === 'string' ? child.value : null))
    .filter((value): value is string => value !== null);
}

function getScopeFilters(
  tree: JsonNode | undefined,
  definitionPrefix?: JsonPath
): {
  stepTypes: string[];
  stepNames: string[];
} {
  const subtree = getDefinitionSubtree(tree, definitionPrefix);
  return {
    stepTypes: getStringArrayAtPath(subtree, ['scope', 'step_types']),
    stepNames: getStringArrayAtPath(subtree, ['scope', 'step_names']),
  };
}

function getJsonPathFieldIndex(path: JsonPath, fieldName: string): number {
  for (let index = path.length - 1; index >= 0; index -= 1) {
    if (path[index] === fieldName) {
      return index;
    }
  }
  return -1;
}

function getRangeForNodeContent(
  monaco: MonacoModule,
  model: import('monaco-editor').editor.ITextModel,
  node: JsonNode | undefined
) {
  if (!node || node.type !== 'string') {
    return null;
  }

  const start = model.getPositionAt(node.offset + 1);
  const end = model.getPositionAt(node.offset + Math.max(node.length - 1, 1));

  return new monaco.Range(
    start.lineNumber,
    start.column,
    end.lineNumber,
    end.column
  );
}

function getDefaultRange(
  monaco: MonacoModule,
  model: import('monaco-editor').editor.ITextModel,
  position: import('monaco-editor').Position
) {
  const word = model.getWordUntilPosition(position);

  return new monaco.Range(
    position.lineNumber,
    word.startColumn,
    position.lineNumber,
    word.endColumn
  );
}

function getReplaceRange(
  monaco: MonacoModule,
  model: import('monaco-editor').editor.ITextModel,
  position: import('monaco-editor').Position,
  node: JsonNode | undefined
) {
  return (
    getRangeForNodeContent(monaco, model, node) ??
    getDefaultRange(monaco, model, position)
  );
}

function getPropertyKeyReplaceRange(
  monaco: MonacoModule,
  model: import('monaco-editor').editor.ITextModel,
  node: JsonNode | undefined
) {
  if (!node || node.type !== 'string') {
    return null;
  }

  const start = model.getPositionAt(node.offset + 1);
  const end = model.getPositionAt(node.offset + node.length);

  return new monaco.Range(
    start.lineNumber,
    start.column,
    end.lineNumber,
    end.column
  );
}

function unescapeJsonPointerSegment(segment: string): string {
  return segment.replace(/~1/g, '/').replace(/~0/g, '~');
}

function resolveJsonPointer(
  rootSchema: JsonSchema | null,
  ref: string
): JsonSchema | null {
  if (!rootSchema || !ref.startsWith('#/')) {
    return null;
  }

  let current: unknown = rootSchema;
  for (const segment of ref
    .slice(2)
    .split('/')
    .map(unescapeJsonPointerSegment)) {
    if (!isObject(current) || !(segment in current)) {
      return null;
    }
    current = current[segment];
  }

  return asSchema(current);
}

function getSchemaTypes(schema: unknown): string[] {
  if (!isObject(schema)) {
    return [];
  }

  if (typeof schema.type === 'string') {
    return [schema.type];
  }

  if (!Array.isArray(schema.type)) {
    return [];
  }

  return schema.type.filter(
    (value): value is string => typeof value === 'string'
  );
}

function getSchemaType(schema: unknown): string | null {
  return getSchemaTypes(schema).find((value) => value !== 'null') ?? null;
}

function getSchemaEnumValues(schema: unknown): unknown[] {
  return isObject(schema) && Array.isArray(schema.enum) ? schema.enum : [];
}

function stripCompositionKeys(schema: JsonSchema): JsonSchema {
  const stripped = { ...schema };
  for (const key of SCHEMA_COMPOSITION_KEYS) {
    delete stripped[key];
  }
  return stripped;
}

function mergeSchemas(
  schemas: JsonSchema[],
  baseSchema?: JsonSchema | null
): JsonSchema {
  const merged: JsonSchema = baseSchema ? stripCompositionKeys(baseSchema) : {};
  const properties: Record<string, unknown> = {};
  const required = new Set<string>();
  const enumValues: unknown[] = [];
  const types = new Set<string>();
  let items: unknown;
  let additionalProperties: unknown;

  for (const schema of schemas) {
    for (const type of getSchemaTypes(schema)) {
      if (type !== 'null') {
        types.add(type);
      }
    }

    for (const value of getSchemaEnumValues(schema)) {
      if (!enumValues.some((candidate) => candidate === value)) {
        enumValues.push(value);
      }
    }

    if (isObject(schema.properties)) {
      Object.assign(properties, schema.properties);
    }

    if (Array.isArray(schema.required)) {
      for (const value of schema.required) {
        if (typeof value === 'string') {
          required.add(value);
        }
      }
    }

    if (items === undefined && schema.items !== undefined) {
      items = schema.items;
    }

    if (
      additionalProperties === undefined &&
      schema.additionalProperties !== undefined
    ) {
      additionalProperties = schema.additionalProperties;
    }

    if (
      merged.description === undefined &&
      typeof schema.description === 'string'
    ) {
      merged.description = schema.description;
    }

    if (merged.title === undefined && typeof schema.title === 'string') {
      merged.title = schema.title;
    }

    if (merged.default === undefined && 'default' in schema) {
      merged.default = schema.default;
    }

    if (
      merged.examples === undefined &&
      Array.isArray(schema.examples) &&
      schema.examples.length > 0
    ) {
      merged.examples = schema.examples;
    }
  }

  if (Object.keys(properties).length > 0) {
    merged.properties = properties;
  }

  if (required.size > 0) {
    merged.required = [...required];
  }

  if (enumValues.length > 0) {
    merged.enum = enumValues;
  }

  if (types.size === 1) {
    merged.type = [...types][0];
  } else if (types.size > 1) {
    merged.type = [...types];
  }

  if (items !== undefined) {
    merged.items = items;
  }

  if (additionalProperties !== undefined) {
    merged.additionalProperties = additionalProperties;
  }

  return merged;
}

function normalizeSchema(
  schema: unknown,
  rootSchema: JsonSchema | null,
  seenRefs: Set<string> = new Set()
): JsonSchema | null {
  const current = asSchema(schema);
  if (!current) {
    return null;
  }

  if (typeof current.$ref === 'string') {
    const ref = current.$ref;
    if (seenRefs.has(ref)) {
      return stripCompositionKeys(current);
    }

    const resolved = resolveJsonPointer(rootSchema, ref);
    if (!resolved) {
      return stripCompositionKeys(current);
    }

    const localOverrides = stripCompositionKeys(current);
    const nextSeenRefs = new Set(seenRefs);
    nextSeenRefs.add(ref);
    const normalizedResolved = normalizeSchema(
      resolved,
      rootSchema,
      nextSeenRefs
    );
    return normalizedResolved
      ? mergeSchemas([normalizedResolved, localOverrides])
      : localOverrides;
  }

  if (Array.isArray(current.allOf) && current.allOf.length > 0) {
    const variants = current.allOf
      .map((variant) => normalizeSchema(variant, rootSchema, seenRefs))
      .filter((variant): variant is JsonSchema => variant !== null);

    if (variants.length > 0) {
      return mergeSchemas(variants, current);
    }
  }

  const union = Array.isArray(current.anyOf)
    ? current.anyOf
    : Array.isArray(current.oneOf)
      ? current.oneOf
      : null;

  if (union && union.length > 0) {
    const variants = union
      .map((variant) => normalizeSchema(variant, rootSchema, seenRefs))
      .filter((variant): variant is JsonSchema => variant !== null);

    const nonNullVariants = variants.filter(
      (variant) => getSchemaType(variant) !== 'null'
    );

    if (nonNullVariants.length > 0) {
      return mergeSchemas(nonNullVariants, current);
    }
  }

  return current;
}

function getSchemaProperties(schema: unknown): Record<string, unknown> {
  const normalized = normalizeSchema(schema, asSchema(schema));
  if (!normalized) {
    return {};
  }

  if (isObject(normalized.properties)) {
    return normalized.properties;
  }

  const propertyEntries = Object.entries(normalized).filter(
    ([key, value]) => !RESERVED_SCHEMA_KEYS.has(key) && isObject(value)
  );

  return Object.fromEntries(propertyEntries);
}

function getSchemaRequiredProperties(schema: unknown): string[] {
  if (!isObject(schema) || !Array.isArray(schema.required)) {
    return [];
  }

  return schema.required.filter(
    (value): value is string => typeof value === 'string'
  );
}

function getSchemaAtProperty(
  schema: JsonSchema | null,
  propertyName: string,
  rootSchema: JsonSchema | null
): JsonSchema | null {
  const normalized = normalizeSchema(schema, rootSchema);
  if (!normalized) {
    return null;
  }

  const properties = getSchemaProperties(normalized);
  if (propertyName in properties) {
    return normalizeSchema(properties[propertyName], rootSchema);
  }

  if (isObject(normalized.additionalProperties)) {
    return normalizeSchema(normalized.additionalProperties, rootSchema);
  }

  return null;
}

function getArrayItemSchema(
  schema: JsonSchema | null,
  rootSchema: JsonSchema | null
): JsonSchema | null {
  const normalized = normalizeSchema(schema, rootSchema);
  if (!normalized) {
    return null;
  }

  return normalizeSchema(normalized.items, rootSchema);
}

function getPropertyKeyContext(
  path: JsonPath,
  isAtPropertyKey: boolean
): { objectPath: JsonPath; replaceExistingKey: boolean } | null {
  if (!isAtPropertyKey || path.length === 0) {
    return null;
  }

  const last = path[path.length - 1];
  if (last === '') {
    return { objectPath: path.slice(0, -1), replaceExistingKey: false };
  }

  if (typeof last === 'string') {
    return { objectPath: path.slice(0, -1), replaceExistingKey: true };
  }

  return null;
}

function isSelectorPathLocation(path: JsonPath): boolean {
  return (
    path.length >= 2 &&
    path[path.length - 1] === 'path' &&
    path[path.length - 2] === 'selector'
  );
}

function isEvaluatorNameLocation(path: JsonPath): boolean {
  return (
    path.length >= 2 &&
    path[path.length - 1] === 'name' &&
    path[path.length - 2] === 'evaluator'
  );
}

function escapeSnippetValue(value: string): string {
  return value.replace(/[\\$}]/g, '\\$&');
}

function toJsonLiteral(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function getSchemaDescription(schema: unknown): string | undefined {
  return isObject(schema) && typeof schema.description === 'string'
    ? schema.description
    : undefined;
}

function getSchemaTitle(schema: unknown): string | undefined {
  return isObject(schema) && typeof schema.title === 'string'
    ? schema.title
    : undefined;
}

function isSchemaWithProperties(
  schema: JsonSchema,
  propertyNames: string[]
): boolean {
  const properties = getSchemaProperties(schema);
  return propertyNames.every((propertyName) => propertyName in properties);
}

function getSchemaExamples(schema: unknown): unknown[] {
  return isObject(schema) && Array.isArray(schema.examples)
    ? schema.examples
    : [];
}

function getSchemaDefault(schema: unknown): unknown {
  return isObject(schema) && 'default' in schema ? schema.default : undefined;
}

function nextSnippetTabStop(
  snippetState: SnippetState,
  defaultValue?: string
): string {
  const tabStop = snippetState.nextTabStop;
  snippetState.nextTabStop += 1;

  if (defaultValue) {
    return `\${${tabStop}:${escapeSnippetValue(defaultValue)}}`;
  }

  return `\${${tabStop}}`;
}

function buildSchemaValueSnippet(
  schema: JsonSchema | null,
  rootSchema: JsonSchema | null,
  snippetState: SnippetState,
  depth = 0
): string {
  const normalized = normalizeSchema(schema, rootSchema);
  if (!normalized || depth > 4) {
    return nextSnippetTabStop(snippetState);
  }

  const enumValues = getSchemaEnumValues(normalized);
  if (enumValues.length > 0) {
    return toJsonLiteral(enumValues[0]);
  }

  const examples = getSchemaExamples(normalized);
  const defaultValue = getSchemaDefault(normalized);
  const preferredValue =
    defaultValue !== undefined ? defaultValue : examples[0];
  const schemaTitle = getSchemaTitle(normalized);

  if (
    schemaTitle === 'ControlSelector' ||
    isSchemaWithProperties(normalized, ['path'])
  ) {
    return '{\n  "path": "*"\n}';
  }

  if (
    schemaTitle === 'EvaluatorSpec' ||
    isSchemaWithProperties(normalized, ['name', 'config'])
  ) {
    return '{\n  "name": "",\n  "config": {}\n}';
  }

  if (
    schemaTitle === 'ControlAction' ||
    isSchemaWithProperties(normalized, ['decision', 'steering_context'])
  ) {
    return '{\n  "decision": "deny"\n}';
  }

  if (
    schemaTitle === 'ControlScope' ||
    isSchemaWithProperties(normalized, ['step_types', 'stages'])
  ) {
    return '{\n  "step_types": ["llm"],\n  "stages": ["post"]\n}';
  }

  if (
    schemaTitle === 'ConditionNode' ||
    isSchemaWithProperties(normalized, [
      'selector',
      'evaluator',
      'and',
      'or',
      'not',
    ])
  ) {
    return '{}';
  }

  switch (getSchemaType(normalized)) {
    case 'object': {
      return '{}';
    }
    case 'array': {
      return '[]';
    }
    case 'boolean': {
      return String(
        typeof preferredValue === 'boolean' ? preferredValue : true
      );
    }
    case 'integer':
    case 'number': {
      return String(typeof preferredValue === 'number' ? preferredValue : 0);
    }
    case 'string': {
      if (typeof preferredValue === 'string' && preferredValue.length > 0) {
        return `"${escapeSnippetValue(preferredValue)}"`;
      }
      return `"${nextSnippetTabStop(snippetState)}"`;
    }
    default: {
      if (preferredValue !== undefined) {
        return toJsonLiteral(preferredValue);
      }
      return 'null';
    }
  }
}

function buildPropertyInsertText(
  propertyName: string,
  propertySchema: JsonSchema | null,
  rootSchema: JsonSchema | null,
  replaceExistingKey = false
): string {
  const snippetState: SnippetState = { nextTabStop: 1 };
  const valueSnippet = buildSchemaValueSnippet(
    propertySchema,
    rootSchema,
    snippetState
  );
  const prefix = replaceExistingKey
    ? `${escapeSnippetValue(propertyName)}": `
    : `"${escapeSnippetValue(propertyName)}": `;
  return `${prefix}${valueSnippet}`;
}

function buildValueInsertText(
  value: unknown,
  isStringValueContext: boolean
): string {
  return typeof value === 'string' && isStringValueContext
    ? value
    : toJsonLiteral(value);
}

function getObjectPropertyNames(node: JsonNode | undefined): Set<string> {
  if (!node || node.type !== 'object' || !node.children) {
    return new Set();
  }

  return new Set(
    node.children
      .map((propertyNode) => {
        const keyNode = propertyNode.children?.[0];
        return typeof keyNode?.value === 'string' ? keyNode.value : null;
      })
      .filter((value): value is string => value !== null)
  );
}

function getExistingKeysFromText(text: string, offset: number): Set<string> {
  let braceDepth = 0;
  let objectStart = -1;
  for (let i = offset - 1; i >= 0; i -= 1) {
    if (text[i] === '}') braceDepth += 1;
    if (text[i] === '{') {
      if (braceDepth === 0) {
        objectStart = i;
        break;
      }
      braceDepth -= 1;
    }
  }
  if (objectStart < 0) return new Set();

  braceDepth = 0;
  let objectEnd = text.length;
  for (let i = objectStart; i < text.length; i += 1) {
    if (text[i] === '{') braceDepth += 1;
    if (text[i] === '}') {
      braceDepth -= 1;
      if (braceDepth === 0) {
        objectEnd = i;
        break;
      }
    }
  }

  const keys = new Set<string>();
  const pattern = /"([^"]+)"\s*:/g;
  let match;
  const slice = text.substring(objectStart, objectEnd + 1);
  while ((match = pattern.exec(slice)) !== null) {
    keys.add(match[1]);
  }
  return keys;
}

function walkSchemaPaths(
  schema: unknown,
  basePath: string,
  output: Set<string>,
  depth = 0
) {
  if (depth > 5) {
    return;
  }

  output.add(basePath);
  const properties = getSchemaProperties(schema);
  for (const [propertyName, propertySchema] of Object.entries(properties)) {
    const childPath = `${basePath}.${propertyName}`;
    output.add(childPath);
    walkSchemaPaths(propertySchema, childPath, output, depth + 1);
  }
}

function buildSelectorPathSuggestions(
  steps: StepSchema[] | undefined,
  tree: JsonNode | undefined,
  definitionPrefix?: JsonPath
): SelectorPathSuggestion[] {
  const suggestions = new Map<string, SelectorPathSuggestion>();
  const { stepTypes, stepNames } = getScopeFilters(tree, definitionPrefix);
  const rankedSteps = steps ?? [];

  for (const rootPath of ROOT_SELECTOR_PATHS) {
    suggestions.set(rootPath, {
      label: rootPath,
      detail: 'Built-in control selector root',
      rank: 0,
    });
  }

  const getStepRank = (step: StepSchema): number => {
    const typeMatches = stepTypes.length === 0 || stepTypes.includes(step.type);
    const nameMatches = stepNames.length === 0 || stepNames.includes(step.name);

    if (typeMatches && nameMatches) return 0;
    if (typeMatches || nameMatches) return 1;
    return 2;
  };

  for (const step of rankedSteps) {
    const rank = getStepRank(step);
    const stepLabel = `${step.type}:${step.name}`;
    const inputPaths = new Set<string>(['input']);
    const outputPaths = new Set<string>(['output']);

    if (step.input_schema) {
      walkSchemaPaths(step.input_schema, 'input', inputPaths);
    }

    if (step.output_schema) {
      walkSchemaPaths(step.output_schema, 'output', outputPaths);
    }

    for (const path of [...inputPaths, ...outputPaths]) {
      const existing = suggestions.get(path);
      if (!existing || rank < existing.rank) {
        suggestions.set(path, {
          label: path,
          detail: stepLabel,
          rank,
        });
      }
    }
  }

  return [...suggestions.values()].sort((left, right) => {
    if (left.rank !== right.rank) {
      return left.rank - right.rank;
    }
    return left.label.localeCompare(right.label);
  });
}

function findEvaluatorById(
  evaluators: JsonEditorEvaluatorOption[] | undefined,
  id: string | null | undefined
): JsonEditorEvaluatorOption | null {
  if (!evaluators || !id) {
    return null;
  }

  return evaluators.find((candidate) => candidate.id === id) ?? null;
}

function resolveActiveEvaluator(
  context: JsonEditorAutocompleteContext,
  tree: JsonNode | undefined,
  path: JsonPath
): JsonEditorEvaluatorOption | null {
  if (context.mode === 'evaluator-config') {
    return findEvaluatorById(context.evaluators, context.activeEvaluatorId);
  }

  // For template mode, strip the definition prefix so that the evaluator
  // index lookup works on relative paths, then reconstruct the absolute
  // tree path for the node lookup.
  const relativePath =
    context.mode === 'template'
      ? stripDefinitionPrefix(path, context.definitionPrefix)
      : path;
  if (!relativePath) return null;

  const evaluatorIndex = getJsonPathFieldIndex(relativePath, 'evaluator');
  if (!tree || evaluatorIndex < 0) {
    return null;
  }

  const prefix = context.definitionPrefix ?? [];
  const evaluatorNamePath = [
    ...prefix,
    ...relativePath.slice(0, evaluatorIndex),
    'evaluator',
    'name',
  ];
  const evaluatorNameNode = findNodeAtLocation(tree, evaluatorNamePath);
  const evaluatorName =
    typeof evaluatorNameNode?.value === 'string'
      ? evaluatorNameNode.value
      : null;

  return findEvaluatorById(context.evaluators, evaluatorName);
}

function getInitialSchemaCursor(
  context: JsonEditorAutocompleteContext,
  activeEvaluator: JsonEditorEvaluatorOption | null
): SchemaCursor {
  if (context.mode === 'evaluator-config') {
    const rootSchema = asSchema(activeEvaluator?.configSchema ?? null);
    return {
      schema: normalizeSchema(rootSchema, rootSchema),
      rootSchema,
    };
  }

  const rootSchema = asSchema(context.schema ?? null);
  return {
    schema: normalizeSchema(rootSchema, rootSchema),
    rootSchema,
  };
}

function isEvaluatorConfigSegment(path: JsonPath, index: number): boolean {
  return (
    typeof path[index] === 'string' &&
    path[index] === 'config' &&
    index > 0 &&
    path[index - 1] === 'evaluator'
  );
}

function resolveSchemaAtJsonPath(
  context: JsonEditorAutocompleteContext,
  activeEvaluator: JsonEditorEvaluatorOption | null,
  path: JsonPath
): SchemaCursor {
  // For template mode, only provide schema resolution inside definition_template.
  // Outside of it (envelope level), return null schema.
  let effectivePath = path;
  if (context.mode === 'template') {
    const relative = stripDefinitionPrefix(path, context.definitionPrefix);
    if (relative === null) {
      return { schema: null, rootSchema: null };
    }
    effectivePath = relative;
  }

  let cursor = getInitialSchemaCursor(context, activeEvaluator);

  for (let index = 0; index < effectivePath.length; index += 1) {
    const segment = effectivePath[index];
    if (!cursor.schema) {
      return cursor;
    }

    if (
      (context.mode === 'control' || context.mode === 'template') &&
      isEvaluatorConfigSegment(effectivePath, index)
    ) {
      const rootSchema = asSchema(activeEvaluator?.configSchema ?? null);
      cursor = {
        schema: normalizeSchema(rootSchema, rootSchema),
        rootSchema,
      };
      continue;
    }

    if (typeof segment === 'number') {
      cursor = {
        schema: getArrayItemSchema(cursor.schema, cursor.rootSchema),
        rootSchema: cursor.rootSchema,
      };
      continue;
    }

    cursor = {
      schema: getSchemaAtProperty(cursor.schema, segment, cursor.rootSchema),
      rootSchema: cursor.rootSchema,
    };
  }

  return cursor;
}

function buildEvaluatorNameSuggestions(
  monaco: MonacoModule,
  range: import('monaco-editor').IRange,
  evaluators: JsonEditorEvaluatorOption[] | undefined,
  isStringValueContext: boolean
) {
  return (evaluators ?? []).map((evaluator, index) => ({
    label: evaluator.id,
    kind: monaco.languages.CompletionItemKind.Value,
    detail:
      evaluator.source === 'agent'
        ? `${evaluator.label} (agent evaluator)`
        : evaluator.label,
    documentation: evaluator.description ?? undefined,
    insertText: buildValueInsertText(evaluator.id, isStringValueContext),
    range,
    sortText: `!0${index.toString().padStart(3, '0')}`,
  }));
}

function buildSelectorSuggestions(
  monaco: MonacoModule,
  range: import('monaco-editor').IRange,
  steps: StepSchema[] | undefined,
  tree: JsonNode | undefined,
  isStringValueContext: boolean,
  definitionPrefix?: JsonPath
) {
  return buildSelectorPathSuggestions(steps, tree, definitionPrefix).map(
    (suggestion, index) => ({
      label: suggestion.label,
      kind: monaco.languages.CompletionItemKind.Value,
      detail: suggestion.detail,
      insertText: buildValueInsertText(suggestion.label, isStringValueContext),
      range,
      sortText: `!${suggestion.rank}${index.toString().padStart(3, '0')}`,
    })
  );
}

// ---------------------------------------------------------------------------
// Template mode: $param and template_values completions
// ---------------------------------------------------------------------------

/**
 * Build completion items for $param references inside definition_template.
 * Offered at value positions as {"$param": "name"} object snippets.
 */
function buildParamRefObjectSuggestions(
  monaco: MonacoModule,
  range: import('monaco-editor').IRange,
  parameterNames: string[] | undefined,
  isStringValueContext: boolean
): import('monaco-editor').languages.CompletionItem[] {
  if (!parameterNames?.length || isStringValueContext) return [];
  return parameterNames.map((name, index) => ({
    label: { label: `\$param: ${name}`, description: 'Template parameter' },
    kind: monaco.languages.CompletionItemKind.Reference,
    detail: 'Insert template parameter reference',
    insertText: `{"\\$param": "${name}"}`,
    range,
    sortText: `!0${index.toString().padStart(3, '0')}`,
  }));
}

/**
 * Build completion items for parameter names inside a {"$param": ""} value.
 */
function buildParamNameSuggestions(
  monaco: MonacoModule,
  range: import('monaco-editor').IRange,
  parameterNames: string[] | undefined,
  isStringValueContext: boolean
): import('monaco-editor').languages.CompletionItem[] {
  if (!parameterNames?.length) return [];
  return parameterNames.map((name, index) => ({
    label: name,
    kind: monaco.languages.CompletionItemKind.Variable,
    detail: 'Template parameter',
    insertText: buildValueInsertText(name, isStringValueContext),
    range,
    sortText: `!0${index.toString().padStart(3, '0')}`,
  }));
}

/**
 * Build property-key completions for template_values (suggest parameter names).
 */
function buildTemplateValueKeySuggestions(
  monaco: MonacoModule,
  range: import('monaco-editor').IRange,
  parameterNames: string[] | undefined,
  tree: JsonNode | undefined,
  replaceExistingKey: boolean,
  _text: string,
  _offset: number
): import('monaco-editor').languages.CompletionItem[] {
  if (!parameterNames?.length) return [];

  // Find which keys already exist in template_values
  const tvNode = tree
    ? findNodeAtLocation(tree, ['template_values'])
    : undefined;
  const existingKeys = new Set<string>();
  if (tvNode?.type === 'object' && tvNode.children) {
    for (const prop of tvNode.children) {
      const key = prop.children?.[0];
      if (key && typeof key.value === 'string') {
        existingKeys.add(key.value);
      }
    }
  }

  return parameterNames
    .filter((name) => !existingKeys.has(name))
    .map((name, index) => {
      const insertText = replaceExistingKey ? name : `"${name}": `;
      return {
        label: name,
        kind: monaco.languages.CompletionItemKind.Property,
        detail: 'Template parameter',
        insertText,
        range,
        sortText: `!0${index.toString().padStart(3, '0')}`,
      };
    });
}

function buildSchemaPropertySuggestions(
  monaco: MonacoModule,
  range: import('monaco-editor').IRange,
  schemaCursor: SchemaCursor,
  tree: JsonNode | undefined,
  objectPath: JsonPath,
  replaceExistingKey: boolean,
  currentPropertyName: string | null,
  text: string,
  offset: number
) {
  if (!schemaCursor.schema) {
