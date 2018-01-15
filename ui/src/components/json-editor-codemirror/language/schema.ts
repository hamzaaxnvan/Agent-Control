import type { JsonSchema } from '@/core/page-components/agent-detail/modals/edit-control/types';

import { SCHEMA_COMPOSITION_KEYS } from './types';

export function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export function asSchema(schema: unknown): JsonSchema | null {
  return isObject(schema) ? schema : null;
}

export function getSchemaTypes(schema: unknown): string[] {
  if (!isObject(schema)) return [];
  if (typeof schema.type === 'string') return [schema.type];
  if (!Array.isArray(schema.type)) return [];
  return schema.type.filter(
    (value): value is string => typeof value === 'string'
  );
}

export function getSchemaType(schema: unknown): string | null {
  return getSchemaTypes(schema).find((value) => value !== 'null') ?? null;
}

export function getSchemaEnumValues(schema: unknown): unknown[] {
  return isObject(schema) && Array.isArray(schema.enum) ? schema.enum : [];
}

export function getSchemaDefault(schema: unknown): unknown {
  return isObject(schema) && 'default' in schema ? schema.default : undefined;
}

export function getSchemaDescription(schema: unknown): string | null {
  return isObject(schema) && typeof schema.description === 'string'
    ? schema.description
    : null;
}

export function getSchemaTitle(schema: unknown): string | null {
  return isObject(schema) && typeof schema.title === 'string'
    ? schema.title
    : null;
}

export function getSchemaProperties(schema: unknown): Record<string, unknown> {
  return isObject(schema) && isObject(schema.properties)
    ? (schema.properties as Record<string, unknown>)
    : {};
}

export function getSchemaRequiredProperties(schema: unknown): string[] {
  if (!isObject(schema) || !Array.isArray(schema.required)) return [];
  return schema.required.filter(
    (value): value is string => typeof value === 'string'
  );
}

function unescapeJsonPointerSegment(segment: string): string {
  return segment.replace(/~1/g, '/').replace(/~0/g, '~');
}

function resolveJsonPointer(
  rootSchema: JsonSchema | null,
  ref: string
): JsonSchema | null {
  if (!rootSchema || !ref.startsWith('#/')) return null;
  let current: unknown = rootSchema;
  for (const segment of ref
    .slice(2)
    .split('/')
    .map(unescapeJsonPointerSegment)) {
    if (!isObject(current) || !(segment in current)) return null;
    current = current[segment];
  }
  return asSchema(current);
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
      if (type !== 'null') types.add(type);
    }
