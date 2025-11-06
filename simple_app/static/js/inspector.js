export function initInspector(panelEl, options = {}) {
  if (!panelEl) {
    return { update() {}, onOpen() {} };
  }

  const tagsEl = panelEl.querySelector('#inspector-tags');
  const linksEl = panelEl.querySelector('#inspector-links');
  const propsEl = panelEl.querySelector('#inspector-properties');
  const sizeSlider = panelEl.querySelector('#inspector-size');
  const sizeNumber = panelEl.querySelector('#inspector-size-value');
  const linkForm = panelEl.querySelector('#inspector-link-form');
  const linkSelect = panelEl.querySelector('#inspector-link-target');
  const linkReason = panelEl.querySelector('#inspector-link-reason');
  const linkStatus = panelEl.querySelector('#inspector-link-status');

  panelEl.querySelector('[data-close-inspector]')?.addEventListener('click', () => {
    panelEl.setAttribute('aria-hidden', 'true');
  });

  let noteOptions = [];
  let optionsLoaded = false;
  let fetchingOptions = false;
  let currentNoteId = null;
  let suppressSizeEvents = false;

  const minWeight = Number.parseFloat(sizeSlider?.min ?? '0.3') || 0.3;
  const maxWeight = Number.parseFloat(sizeSlider?.max ?? '5') || 5;

  sizeSlider?.addEventListener('input', (event) => {
    if (suppressSizeEvents) return;
    const value = clampWeight(event.target.value, minWeight, maxWeight);
    syncSizeInputs(value, { updateNumber: true, updateSlider: false });
    options.onSetLayoutHint?.('sizeWeight', value);
    setStatus('');
  });

  sizeNumber?.addEventListener('change', (event) => {
    const value = clampWeight(event.target.value, minWeight, maxWeight);
    syncSizeInputs(value, { updateNumber: true, updateSlider: true });
    options.onSetLayoutHint?.('sizeWeight', value);
    setStatus('');
  });

  linkForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (typeof options.onCreateLink !== 'function') return;
    const targetId = linkSelect?.value;
    if (!targetId) {
      setStatus('Выберите заметку для связи', true);
      return;
    }
    if (targetId === currentNoteId) {
      setStatus('Нельзя связать заметку саму с собой', true);
      return;
    }
    toggleLinkForm(true);
    setStatus('Сохраняем…');
    try {
      await options.onCreateLink({
        toId: targetId,
        reason: linkReason?.value?.trim() || '',
      });
      if (linkReason) linkReason.value = '';
      if (linkSelect) linkSelect.value = '';
      setStatus('Связь добавлена');
    } catch (error) {
      const message = error?.message || 'Не удалось добавить связь';
      setStatus(message, true);
    } finally {
      toggleLinkForm(false);
    }
  });

  async function ensureNoteOptions(force = false) {
    if (!force && optionsLoaded) return noteOptions;
    if (fetchingOptions || typeof options.fetchNoteOptions !== 'function') return noteOptions;
    fetchingOptions = true;
    try {
      const list = await options.fetchNoteOptions();
      if (Array.isArray(list)) {
        noteOptions = list;
        optionsLoaded = true;
      }
    } catch (error) {
      setStatus('Не удалось загрузить заметки для связи', true);
    } finally {
      fetchingOptions = false;
    }
    return noteOptions;
  }

  function populateLinkOptions(note) {
    if (!linkSelect) return;
    const previous = linkSelect.value;
    linkSelect.innerHTML = '';

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Выберите заметку';
    placeholder.disabled = true;
    placeholder.selected = true;
    linkSelect.appendChild(placeholder);

    noteOptions
      .filter((option) => option.id && option.id !== note?.id)
      .forEach((option) => {
        const opt = document.createElement('option');
        opt.value = option.id;
        opt.textContent = option.title || option.id;
        if (option.id === previous) opt.selected = true;
        linkSelect.appendChild(opt);
      });

    const availableTargets = noteOptions.filter((option) => option.id && option.id !== note?.id).length;
    linkSelect.disabled = fetchingOptions || availableTargets === 0;
    if (!fetchingOptions && availableTargets === 0 && !linkStatus?.textContent) {
      setStatus('Добавьте ещё заметку, чтобы связать её с текущей');
    }
  }

  function syncSizeInputs(value, { updateNumber = true, updateSlider = true } = {}) {
    const fixed = Number.isFinite(value) ? Math.round(value * 10) / 10 : 1;
    suppressSizeEvents = true;
    if (updateSlider && sizeSlider) {
      sizeSlider.value = fixed.toString();
    }
    if (updateNumber && sizeNumber) {
      sizeNumber.value = fixed.toFixed(1);
    }
    suppressSizeEvents = false;
  }

  function toggleLinkForm(disabled) {
    linkForm?.querySelectorAll('select, input, button').forEach((el) => {
      el.disabled = disabled;
    });
  }

  function setStatus(message, isError = false) {
    if (!linkStatus) return;
    linkStatus.textContent = message || '';
    linkStatus.classList.toggle('error', Boolean(isError && message));
  }

  return {
    async onOpen(note) {
      currentNoteId = note?.id || null;
      await ensureNoteOptions();
      populateLinkOptions(note);
    },
    update(note) {
      currentNoteId = note?.id || null;
      renderTags(tagsEl, note?.tags || []);
      renderLinks(linksEl, note?.linksFrom || [], note?.linksTo || []);
      renderProperties(propsEl, note?.passport || {});
      const weight = clampWeight(note?.layoutHints?.sizeWeight, minWeight, maxWeight);
      syncSizeInputs(weight, { updateNumber: true, updateSlider: true });
    },
  };
}

function renderTags(container, tags) {
  if (!container) return;
  container.innerHTML = '';
  tags.forEach((tag) => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.textContent = tag;
    container.appendChild(chip);
  });
}

function renderLinks(container, fromLinks, toLinks) {
  if (!container) return;
  container.innerHTML = '';
  const entries = [];
  (fromLinks || []).forEach((link) => entries.push({ ...link, direction: 'out' }));
  (toLinks || []).forEach((link) => entries.push({ ...link, direction: 'in' }));

  if (!entries.length) {
    const empty = document.createElement('li');
    empty.className = 'muted';
    empty.textContent = 'Связей пока нет';
    container.appendChild(empty);
    return;
  }

  entries.forEach((link) => {
    const li = document.createElement('li');
    li.className = 'link-list-item';

    const targetId = link.direction === 'out' ? link.toId : link.fromId;
    const anchor = document.createElement('a');
    anchor.href = `/notes/${targetId}`;
    anchor.textContent = link.title || targetId;
    li.append(anchor);

    const meta = document.createElement('span');
    meta.className = 'link-meta muted';
    const arrow = link.direction === 'out' ? '→' : '←';
    const reason = link.reason ? ` · ${link.reason}` : '';
    const directionText = link.direction === 'out' ? 'к заметке' : 'из заметки';
    meta.textContent = `${arrow} ${directionText}${reason}`;
    li.append(meta);

    container.appendChild(li);
  });
}

function renderProperties(container, passport) {
  if (!container) return;
  container.innerHTML = '';
  Object.entries(passport || {}).forEach(([key, value]) => {
    const dt = document.createElement('dt');
    dt.textContent = key;
    const dd = document.createElement('dd');
    dd.textContent = formatValue(value);
    container.append(dt, dd);
  });
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (value && typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value ?? '');
}

function clampWeight(value, min, max) {
  const numeric = Number.parseFloat(value);
  if (Number.isNaN(numeric)) {
    const fallback = Math.max(min, Math.min(max, 1));
    return fallback;
  }
  return Math.max(min, Math.min(max, numeric));
}
