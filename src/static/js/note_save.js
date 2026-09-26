// A failed request never acknowledges a draft. Only the captured revision can be saved.
const clone = value => JSON.parse(JSON.stringify(value));
export const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function mergeRemote(base, local, remote) {
  const result = clone(remote);
  for (const key of Object.keys(local)) {
    if (key === 'blocks') continue;
    if (!same(local[key], base[key])) {
      if (!same(remote[key], base[key]) && !same(remote[key], local[key])) {
        throw new Error('На сервере изменено то же поле. Локальный черновик сохранён.');
      }
      result[key] = clone(local[key]);
    }
  }
  const byId = blocks => new Map(blocks.map(b => [b.id, b]));
  const before = byId(base.blocks), ours = byId(local.blocks), theirs = byId(remote.blocks);
  if ([base, local, remote].some(n => n.blocks.some(b => !b.id))) {
    if (!same(base.blocks, local.blocks)) throw new Error('Конфликт старых блоков. Черновик сохранён.');
    return result;
  }
  for (const [id, block] of before) {
    if (!same(ours.get(id), block)) {
      if (!same(theirs.get(id), block) && !same(theirs.get(id), ours.get(id))) {
        throw new Error('Один блок изменён одновременно. Локальный черновик сохранён.');
      }
      if (ours.has(id)) theirs.set(id, ours.get(id));
      else theirs.delete(id);
    }
  }
  for (const [id, block] of ours) if (!before.has(id)) {
    if (theirs.has(id) && !same(theirs.get(id), block)) throw new Error('Конфликт идентификаторов блоков');
    theirs.set(id, block);
  }
  // Preserve either side's reordering; conflicting reorderings require explicit recovery.
  const order = blocks => blocks.filter(b => before.has(b.id) && ours.has(b.id) && theirs.has(b.id)).map(b => b.id);
  const baseOrder = order(base.blocks), localOrder = order(local.blocks), remoteOrder = order(remote.blocks);
  const localReorder = !same(baseOrder, localOrder);
  if (localReorder && !same(baseOrder, remoteOrder) && !same(localOrder, remoteOrder)) throw new Error('Конфликт порядка блоков');
  const ordered = (localReorder ? local.blocks : remote.blocks).map(b => b.id);
  for (const b of local.blocks) if (!ordered.includes(b.id)) {
    const previous = local.blocks[local.blocks.indexOf(b) - 1]?.id;
    const index = previous ? ordered.indexOf(previous) + 1 : 0;
    ordered.splice(index, 0, b.id);
  }
  for (const b of remote.blocks) if (!ordered.includes(b.id)) {
    const previous = remote.blocks[remote.blocks.indexOf(b) - 1]?.id;
    ordered.splice(previous ? ordered.indexOf(previous) + 1 : 0, 0, b.id);
  }
  result.blocks = ordered.filter(id => theirs.has(id)).map(id => clone(theirs.get(id)));
  return result;
}

export function createNoteSaver({ send, store, onState = () => {}, delay = 600, online = () => true }) {
  let base, pending, revision = 0, acknowledged = 0, flight = null, timer = null;
  let paused = false, retries = 0, storageError = false, state = 'clean';
  const dirty = () => revision !== acknowledged;
  function notify(next, error = null) {
    state = next;
    onState({ state, dirty: dirty(), storageError, error });
  }
  function persist() {
    try {
      if (dirty()) store.write({ base, pending });
      else store.clear();
      storageError = false;
    } catch (_) { storageError = true; }
  }
  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; flush(); }, ms);
  }
  async function flush() {
    clearTimeout(timer); timer = null;
    if (flight) return flight;
    if (paused) return !dirty();
    if (!dirty()) return true;
    if (!online()) { persist(); notify('offline'); return false; }
    // Defer the loop so even a synchronously throwing send() clears flight correctly.
    flight = Promise.resolve().then(async () => {
      while (dirty() && !paused) {
        const version = revision, snapshot = clone(pending);
        notify('saving');
        try { await send(snapshot); }
        catch (error) {
          persist(); notify(online() ? 'save_failed' : 'offline', error);
          if (!paused && online() && ++retries <= 3) schedule(1000 * 2 ** retries);
          return false;
        }
        acknowledged = version;
        base = snapshot;
        retries = 0;
        persist();
      }
      clearTimeout(timer); timer = null;
      notify(dirty() ? 'dirty' : 'clean');
      return !dirty();
    }).finally(() => { flight = null; });
    return flight;
  }
  return {
    get base() { return base === undefined ? undefined : clone(base); },
    get dirty() { return dirty(); },
    get state() { return state; },
    get paused() { return paused; },
    acceptSaved(payload) {
      if (flight) throw new Error('Cannot replace an in-flight save');
      clearTimeout(timer);
      base = clone(payload); pending = clone(payload); acknowledged = ++revision;
      notify('clean'); // Recovery storage is cleared only after an acknowledged save.
    },
    change(payload) {
      if (same(payload, pending)) return;
      pending = clone(payload); revision++; persist(); notify('dirty');
      if (!paused) schedule(delay);
    },
    pause() { paused = true; clearTimeout(timer); },
    resume() { paused = false; if (dirty()) schedule(delay); },
    checkpoint() { persist(); },
    flush,
  };
}
