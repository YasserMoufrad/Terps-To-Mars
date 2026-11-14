import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('GitHub Pages base path matches repository name', () => {
  const config = readFileSync(new URL('../vite.config.ts', import.meta.url), 'utf8');
  assert.match(config, /base: '\/Terps-To-Mars\/'/);
});
