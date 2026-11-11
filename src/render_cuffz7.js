export function render(rows, draw) {
  const out = new Array(rows.length);
  for (let i = 0; i < rows.length; i += 1) out[i] = draw(rows[i]);
  return out;
}
