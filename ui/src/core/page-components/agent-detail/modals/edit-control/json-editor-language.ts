import {
  findNodeAtLocation,
  findNodeAtOffset,
  getLocation,
  type Node as JsonNode,
  type ParseError,
  parseTree,
} from 'jsonc-parser';

import type { StepSchema } from '@/core/api/types';

import type {
  JsonEditorEvaluatorOption,
  JsonEditorMode,
  JsonSchema,
} from './types';

type MonacoModule = typeof import('monaco-editor');
type JsonPath = Array<string | number>;

type JsonEditorAutocompleteContext = {
  mode: JsonEditorMode;
  modelUri: string;
  schema?: JsonSchema | null;
  evaluators?: JsonEditorEvaluatorOption[];
  activeEvaluatorId?: string | null;
  steps?: StepSchema[];
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

function getScopeFilters(tree: JsonNode | undefined): {
  stepTypes: string[];
  stepNames: string[];
} {
  return {
    stepTypes: getStringArrayAtPath(tree, ['scope', 'step_types']),
    stepNames: getStringArrayAtPath(tree, ['scope', 'step_names']),
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
