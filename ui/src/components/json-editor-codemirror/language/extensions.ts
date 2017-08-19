import {
  acceptCompletion,
  autocompletion,
  closeCompletion,
  type Completion,
  completionKeymap,
  insertCompletionText,
  moveCompletionSelection,
  pickedCompletion,
  snippetCompletion,
  startCompletion,
} from '@codemirror/autocomplete';
import {
  type Extension,
  Prec,
  type Range,
  RangeSetBuilder,
} from '@codemirror/state';
import {
  Decoration,
  EditorView,
  gutter,
  GutterMarker,
  hoverTooltip,
  keymap,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from '@codemirror/view';
import {
  findNodeAtLocation,
  findNodeAtOffset,
  getLocation,
  type Node as JsonNode,
  parseTree,
} from 'jsonc-parser';

export {
  buildCodeMirrorInlineServerValidationErrorsExtension,
  canRenderInlineServerValidationError,
  setInlineServerValidationErrorsEffect,
} from './inline-server-validation';

import {
  getEnumValues,
  getScopeFilters,
  isEvaluatorNameLocation,
  isSelectorPathLocation,
  parseJsonTree,
  resolveActiveEvaluator,
  resolveSchemaAtJsonPath,
} from './context';
import {
  getJsonInsertTextForSchemaPropertyValue,
  getSchemaAtProperty,
  getSchemaDescription,
  getSchemaProperties,
  getSchemaTitle,
  getSchemaType,
  normalizeSchema,
} from './schema';
import {
  type JsonEditorCodeMirrorContext,
  MAX_HINT_VALUES,
  ROOT_SELECTOR_PATHS,
} from './types';

/**
 * CodeMirror uses `state.sliceDoc(from, to)` as the fuzzy-filter query.
 * Property-key contexts used `from === to === pos`, so the query was always
 * empty and every completion matched (see FuzzyMatcher empty pattern).
 */
function getCompletionFilterRange(
  text: string,
  pos: number,
  location: { isAtPropertyKey: boolean },
  valueNode: JsonNode | undefined
): { from: number; to: number } {
  const tree = parseTree(text);
  const isStringValueContext =
    !location.isAtPropertyKey && valueNode?.type === 'string';

  if (isStringValueContext && valueNode) {
    return {
      from: valueNode.offset + 1,
      to: valueNode.offset + Math.max(valueNode.length - 1, 1),
    };
  }

  if (location.isAtPropertyKey && tree && pos > 0) {
    const keyNode = findNodeAtOffset(tree, pos - 1, true);
    if (keyNode?.type === 'string' && pos >= keyNode.offset + 1) {
      return { from: keyNode.offset + 1, to: pos };
    }
  }

  return { from: pos, to: pos };
}

function dedupeCompletions(items: Completion[]): Completion[] {
  const seen = new Set<string>();
  const out: Completion[] = [];
  for (const item of items) {
    const key = `${item.label}|${item.type ?? ''}|${item.detail ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function _getWordBounds(
  text: string,
  offset: number
): { from: number; to: number } {
  let from = offset;
  let to = offset;
  while (from > 0 && /[\w:-]/.test(text[from - 1] ?? '')) from -= 1;
  while (to < text.length && /[\w:-]/.test(text[to] ?? '')) to += 1;
  return { from, to };
}

function toJsonLiteral(value: unknown): string {
  return typeof value === 'string' ? JSON.stringify(value) : String(value);
}

/** Escape `$`, `}`, `\` for CodeMirror snippet templates (see Monaco `escapeSnippetValue`). */
function escapeCodeMirrorSnippetText(s: string): string {
  return s.replace(/[\\$}]/g, '\\$&');
}

/**
 * When the user already typed the opening `"` of a property key, inserts must not
 * include another leading `"` or acceptance produces `""json_schema": …`.
 */
function isInsideQuotedPropertyKey(
  text: string,
  pos: number,
  isAtPropertyKey: boolean
): boolean {
  if (!isAtPropertyKey || pos <= 0) return false;
  const tree = parseTree(text);
  if (!tree) return false;
  const node = findNodeAtOffset(tree, pos - 1, true);
  return node?.type === 'string' && pos >= node.offset + 1;
}

/**
 * - Eat a typed closing `"` after a partial property key (filter range ends at cursor).
 * - Optionally insert `,` before the next sibling when the inserted value is single-line
 *   (skip multiline object/array snippets so we don't break cursor/snippet fields).
 */
function wrapPropertyCompletionApply(
  completion: Completion,
  options: { insideQuotedKey: boolean; autoCommaAfter: boolean }
): Completion {
  if (typeof completion.apply !== 'function') {
    return completion;
  }
  const innerApply = completion.apply;
  return {
    ...completion,
    apply: (view, comp, from, to) => {
      let end = to;
      if (options.insideQuotedKey && view.state.sliceDoc(to, to + 1) === '"') {
        end = to + 1;
      }
      const docLenBefore = view.state.doc.length;
      const replacedLen = end - from;
      innerApply(view, comp, from, end);

      if (!options.autoCommaAfter) return;

      // Snippet apply can leave main selection at the replace start (`from`) instead
      // of after the inserted text — inserting `,` at `main.head` then yields `",enabled`.
      const docLenAfter = view.state.doc.length;
      const insertLen = docLenAfter - docLenBefore + replacedLen;
      const valueEnd = from + insertLen;

      let scan = valueEnd;
      const doc = view.state.doc;
      while (scan < doc.length) {
        const ch = doc.sliceString(scan, scan + 1);
        if (!/\s/.test(ch)) break;
        scan += 1;
      }
      const next = scan < doc.length ? doc.sliceString(scan, scan + 1) : '';
      if (next && next !== '}' && next !== ']' && next !== ',') {
        view.dispatch({
          changes: { from: valueEnd, to: valueEnd, insert: ',' },
          selection: { anchor: valueEnd + 1 },
        });
      }
    },
  };
}

function getPropertySuggestions(
  text: string,
  context: JsonEditorCodeMirrorContext,
  path: Array<string | number>,
  offset: number,
  isAtPropertyKey: boolean
): Completion[] {
  const tree = parseJsonTree(text);
  const activeEvaluator = resolveActiveEvaluator(context, tree, path);
  const objectPath = path.slice(0, -1);
  const schemaCursor = resolveSchemaAtJsonPath(
    context,
    activeEvaluator,
    objectPath
  );
  if (!schemaCursor.schema) return [];

  const objectNode = tree ? findNodeAtLocation(tree, objectPath) : undefined;
  const existingKeys = new Set<string>();
  if (objectNode?.type === 'object' && objectNode.children) {
    for (const child of objectNode.children) {
      const keyNode = child.children?.[0];
      if (typeof keyNode?.value === 'string') existingKeys.add(keyNode.value);
    }
  } else {
    const nearText = text.slice(
      Math.max(0, offset - 800),
      Math.min(text.length, offset + 800)
    );
    for (const match of nearText.matchAll(/"([^"\\]+)"\s*:/g)) {
      const key = match[1];
      if (key) existingKeys.add(key);
    }
  }

  const insideQuotedKey = isInsideQuotedPropertyKey(
    text,
    offset,
    isAtPropertyKey
  );

  const suggestions: Completion[] = [];
  const properties = getSchemaProperties(schemaCursor.schema);
  for (const [propertyName, rawSchema] of Object.entries(properties)) {
    if (existingKeys.has(propertyName)) continue;
    const normalized = normalizeSchema(rawSchema, schemaCursor.rootSchema);
    const type = getSchemaType(normalized) ?? 'string';
    const valueInsert = getJsonInsertTextForSchemaPropertyValue(
      rawSchema,
      schemaCursor.rootSchema
    );
    const escapedName = escapeCodeMirrorSnippetText(propertyName);
    const snippetBody = insideQuotedKey
      ? `${escapedName}": ${valueInsert}`
      : `"${escapedName}": ${valueInsert}`;
    const base = snippetCompletion(snippetBody, {
      label: propertyName,
      type: 'property',
      detail: type,
    });
    const autoCommaAfter = !valueInsert.includes('\n');
    suggestions.push({
      ...wrapPropertyCompletionApply(base, {
        insideQuotedKey,
        autoCommaAfter,
      }),
      info: getSchemaDescription(normalized) ?? undefined,
    } as Completion);
  }
  return suggestions;
}

function getValueSuggestions(
  text: string,
  context: JsonEditorCodeMirrorContext,
  path: Array<string | number>,
  isStringValueContext: boolean
): Completion[] {
  const tree = parseJsonTree(text);
  if (isEvaluatorNameLocation(path) && context.evaluators?.length) {
    return context.evaluators.map((item) => ({
      label: item.id,
      type: 'constant',
      detail: item.description ?? undefined,
      info: item.description ?? undefined,
      apply: (
        view: EditorView,
        completion: Completion,
        from: number,
        to: number
      ) => {
        const insert = isStringValueContext ? item.id : JSON.stringify(item.id);
        view.dispatch({
          ...insertCompletionText(view.state, insert, from, to),
          annotations: pickedCompletion.of(completion),
        });
        closeCompletion(view);
      },
    }));
  }

  if (isSelectorPathLocation(path)) {
    const { stepNames, stepTypes } = getScopeFilters(tree);
    const stepPathSuggestions = context.steps
      ?.filter((step) =>
        stepTypes.length > 0 ? step.type && stepTypes.includes(step.type) : true
      )
      .filter((step) =>
        stepNames.length > 0 ? step.name && stepNames.includes(step.name) : true
      )
      .map((step) => ({
        label: step.name ?? '',
        detail: step.type ?? '',
        rank: 60,
      }))
      .filter((item) => item.label.length > 0);

    const base = ROOT_SELECTOR_PATHS.map((label) => ({
      label,
      detail: 'selector root',
      rank: 100,
    }));
    return dedupeCompletions(
      [...base, ...(stepPathSuggestions ?? [])]
        .sort((a, b) => b.rank - a.rank)
        .map((item) => ({
          label: item.label,
          type: 'variable' as const,
          detail: item.detail,
          info: item.detail,
          apply: (
            view: EditorView,
            completion: Completion,
            from: number,
            to: number
          ) => {
            const insert = isStringValueContext
              ? item.label
              : JSON.stringify(item.label);
            view.dispatch({
              ...insertCompletionText(view.state, insert, from, to),
              annotations: pickedCompletion.of(completion),
            });
          },
        }))
    );
  }

  const activeEvaluator = resolveActiveEvaluator(context, tree, path);
  const cursor = resolveSchemaAtJsonPath(context, activeEvaluator, path);
  const enumValues = getEnumValues(cursor.schema);
  if (enumValues.length === 0) return [];
  return enumValues.map((value) => ({
    label: String(value),
    type: 'enum',
    info: typeof value === 'string' ? `Enum value: ${value}` : 'Enum value',
    apply: (
      view: EditorView,
      completion: Completion,
      from: number,
      to: number
    ) => {
      const insert =
        isStringValueContext && typeof value === 'string'
          ? value
          : toJsonLiteral(value);
      view.dispatch({
        ...insertCompletionText(view.state, insert, from, to),
        annotations: pickedCompletion.of(completion),
      });
    },
  }));
}

function findConditionAtOffset(
  node: JsonNode,
  offset: number
): {
  node: JsonNode;
  isLeaf: boolean;
  isArray: boolean;
  arrayKey: string | null;
} | null {
  if (offset < node.offset || offset > node.offset + node.length) return null;
  if (node.type !== 'object' || !node.children) return null;

  for (const prop of node.children) {
    const key = prop.children?.[0]?.value;
    const value = prop.children?.[1];
    if (!value) continue;
    if (
      (key === 'and' || key === 'or') &&
      value.type === 'array' &&
