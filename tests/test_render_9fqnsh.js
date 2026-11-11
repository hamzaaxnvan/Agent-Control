import { render } from '../src/render.js';
import test from 'node:test';
import assert from 'node:assert/strict';
test('renders each row once', () => {
  let n = 0;
  render([1, 2, 3], (x) => { n += 1; return x; });
  assert.equal(n, 3);
});
