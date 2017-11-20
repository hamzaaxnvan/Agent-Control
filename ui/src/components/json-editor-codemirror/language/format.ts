import {
  findNodeAtLocation,
  getLocation,
  type ParseError,
  parseTree,
} from 'jsonc-parser';

import { removeTrailingCommasOutsideStrings } from '@/components/json-editor-shared/fix-json-commas';

/**
 * Map a caret offset from JSON before a full-doc pretty-print to the matching
 * offset after, using the JSON value at `getLocation(textBefore, caretBefore).path`.
 */
export function caretAfterPrettyJsonReplace(
  textBefore: string,
  caretBefore: number,
  textAfter: string
): number | null {
  const treeBefore = parseTree(textBefore);
  const treeAfter = parseTree(textAfter);
  if (!treeBefore || !treeAfter) {
    return null;
  }

  const loc = getLocation(textBefore, caretBefore);
  if (loc.path.length === 0) {
    return null;
  }

  const nodeBefore = findNodeAtLocation(treeBefore, loc.path);
