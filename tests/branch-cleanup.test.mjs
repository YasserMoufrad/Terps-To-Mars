import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const yaml = readFileSync(new URL('../.github/workflows/delete-merged-branch.yml', import.meta.url), 'utf8').replaceAll('\r\n', '\n');
const source = yaml.split('          script: |\n')[1].split('\n').map(line => line.slice(12)).join('\n');
const run = new (Object.getPrototypeOf(async function () {}).constructor)('context', 'github', 'core', source);

async function cleanup({ dependents = [], sha = 'head', fork = false, failure } = {}) {
  // dependents models stacked PRs; sha models newer commits; logs expose the actual decision.
  const logs = [], deleted = [];
  const context = { repo: { owner: 'team', repo: 'mars' }, runId: 42,
    payload: { repository: { full_name: 'team/mars', default_branch: 'main' },
      pull_request: { number: 5, base: { ref: 'main' }, head: { ref: 'pipeline/work', sha: 'head', repo: { full_name: fork ? 'fork/mars' : 'team/mars' } } } } };
  const github = { rest: { pulls: { list: async () => ({ data: dependents }) }, git: {
    getRef: async () => { if (failure) throw failure; return { data: { object: { sha } } }; },
    deleteRef: async request => { deleted.push(request.ref); },
  } } };
  await run(context, github, { info: value => logs.push(JSON.parse(value)) });
  return { logs, deleted };
}

test('cleanup preserves the base of an open stacked PR and logs why', async () => {
  // A dependent PR must stay open; deleting its base would close it.
  const { logs, deleted } = await cleanup({ dependents: [{ number: 6 }] });
  assert.deepEqual(deleted, []);
  assert.equal(logs[0].reason, 'base_of_open_pull_request');
  assert.equal(logs[0].stage, 'branch_cleanup');
  assert.equal(logs[0].run_id, '42');
  assert.ok(Number.isFinite(Date.parse(logs[0].timestamp)));
});

test('cleanup deletes only unchanged same-repository branches', async () => {
  // Newer commits and fork ownership independently prevent deletion.
  assert.deepEqual((await cleanup()).deleted, ['heads/pipeline/work']);
  assert.deepEqual((await cleanup({ sha: 'new-head' })).deleted, []);
  assert.deepEqual((await cleanup({ fork: true })).deleted, []);
});

test('cleanup treats missing branches as expected but propagates other errors', async () => {
  // failure emulates a GitHub API response without making external requests.
  const missing = Object.assign(new Error('missing'), { status: 404 });
  assert.equal((await cleanup({ failure: missing })).logs[0].event, 'branch_missing');
  await assert.rejects(cleanup({ failure: new Error('service failure') }), /service failure/);
});
