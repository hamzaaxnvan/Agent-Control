export function removeTrailingCommasOutsideStrings(text: string): string {
  let fixed = '';
  let inString = false;
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (char === '"' && !escaped) {
      inString = !inString;
      fixed += char;
      continue;
    }

    if (inString) {
      escaped = char === '\\' ? !escaped : false;
      fixed += char;
      continue;
    }

    if (char === ',') {
      let lookahead = index + 1;
