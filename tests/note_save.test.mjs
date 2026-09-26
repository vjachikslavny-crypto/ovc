import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../src/static/js/note_save.js', import.meta.url), 'utf8');
const { createNoteSaver, mergeRemote } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const block = (id, text) => ({ id, type: 'paragraph', data: { parts: [{ text }] } });
const payload = text => ({ title: 'Note', blocks: [block('one', text)], layoutHints: {}, passport: {}, styleTheme: 'dark' });
const tick = () => new Promise(resolve => setImmediate(resolve));
function setup(send) {
  const disk = { value: null };
  const states = [];
  const saver = createNoteSaver({ send, delay: 60000, store: {
    write: data => { disk.value = JSON.parse(JSON.stringify(data)); },
    clear: () => { disk.value = null; },
  }, onState: state => states.push(state) });
  saver.acceptSaved(payload('old'));
  return { saver, disk, states };
}

test('failed PATCH preserves dirty content, retry acknowledges it', async () => {
  let fail = true;
  const { saver, disk } = setup(async () => { if (fail) throw new Error('503'); });
  saver.change(payload('new'));
  assert.equal(await saver.flush(), false);
  assert.equal(saver.state, 'save_failed');
  assert.equal(saver.dirty, true);
  assert.equal(disk.value.pending.blocks[0].data.parts[0].text, 'new');
  fail = false;
  assert.equal(await saver.flush(), true);
  assert.equal(saver.dirty, false);
  assert.equal(disk.value, null);
});

test('older acknowledgment cannot clean a newer edit; requests are sequential', async () => {
  const requests = [];
  const resolvers = [];
  const { saver, disk } = setup(data => { requests.push(data); return new Promise(r => resolvers.push(r)); });
  const mutable = payload('first');
  saver.change(mutable);
  const saving = saver.flush();
  await tick();
  mutable.blocks[0].data.parts[0].text = 'second';
  saver.change(mutable);
  assert.equal(requests[0].blocks[0].data.parts[0].text, 'first');
  resolvers.shift()(); await tick();
  assert.equal(saver.dirty, true);
  assert.equal(disk.value.pending.blocks[0].data.parts[0].text, 'second');
  assert.equal(requests.length, 2);
  resolvers.shift()();
  assert.equal(await saving, true);
});

test('navigation flush bypasses debounce', async () => {
  const requests = [];
  const { saver } = setup(async p => requests.push(p));
  saver.change(payload('immediate navigation'));
  assert.equal(await saver.flush(), true);
  assert.equal(requests[0].blocks[0].data.parts[0].text, 'immediate navigation');
});

test('offline and failed local storage leave warning/dirty state', async () => {
  let latest;
  const saver = createNoteSaver({ send: async () => {}, online: () => false,
    store: { write() { throw new Error('quota'); }, clear() {} }, onState: s => { latest = s; } });
  saver.acceptSaved(payload('base')); saver.change(payload('draft'));
  assert.equal(await saver.flush(), false);
  assert.equal(latest.state, 'offline');
  assert.equal(latest.storageError, true);
  assert.equal(saver.dirty, true);
  saver.pause();
});

test('AI insertion merges with concurrent text edits, attachments and reordering', () => {
  const base = payload('base'); base.blocks.push(block('two', 'second'));
  const local = structuredClone(base);
  local.blocks[0] = block('one', 'typed while AI commits');
  local.blocks.reverse(); local.blocks.push(block('upload', 'attached'));
  const remote = structuredClone(base); remote.blocks.splice(1, 0, block('ai', 'AI result'));
  const merged = mergeRemote(base, local, remote);
  assert.deepEqual(new Set(merged.blocks.map(b => b.id)), new Set(['one', 'two', 'ai', 'upload']));
  assert.equal(merged.blocks.find(b => b.id === 'one').data.parts[0].text, 'typed while AI commits');
  assert.equal(merged.blocks[0].id, 'two');
});

test('conflicting concurrent block updates are rejected without changing either copy', () => {
  const base = payload('base'), local = payload('ours'), remote = payload('theirs');
  assert.throws(() => mergeRemote(base, local, remote), /одновременно/);
  assert.equal(local.blocks[0].data.parts[0].text, 'ours');
  assert.equal(remote.blocks[0].data.parts[0].text, 'theirs');
});

test('paused reconciliation cannot PATCH over an uncertain AI commit', async () => {
  let calls = 0;
  const { saver, disk } = setup(async () => { calls++; });
  saver.pause(); saver.change(payload('pending during AI'));
  assert.equal(await saver.flush(), false);
  assert.equal(calls, 0);
  assert.ok(disk.value.pending);
  saver.resume(); await saver.flush(); assert.equal(calls, 1);
});
