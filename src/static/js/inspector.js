export function initInspector(panelEl, options = {}) {
  if (!panelEl) {
    return { update() {}, onOpen() {} };
  }

  const tagsEl = panelEl.querySelector('#inspector-tags');
  const availableTagsEl = panelEl.querySelector('#inspector-available-tags');
  const tagForm = panelEl.querySelector('#inspector-tag-form');
  const tagInput = panelEl.querySelector('#inspector-tag-input');
  const tagStatus = panelEl.querySelector('#inspector-tag-status');
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
  let allTags = [];
  let tagsLoaded = false;

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

  // Обработчик формы тегов
  const handleTagSubmit = async (event) => {
    console.log('[Inspector] Tag form/button triggered');
    if (event) event.preventDefault();
    
    if (typeof options.onAddTags !== 'function') {
      console.error('[Inspector] onAddTags is not a function!');
      return;
    }
    
    const raw = tagInput?.value || '';
    console.log('[Inspector] Raw input:', raw);
    
    const tags = normalizeTags(raw);
    console.log('[Inspector] Normalized tags:', tags);
    
    if (!tags.length) {
      setTagStatus('Введите тег', true);
      return;
    }
    
    toggleTagForm(true);
    setTagStatus('Сохраняем…');
    
    try {
      console.log('[Inspector] Calling onAddTags with:', tags);
      const result = await options.onAddTags(tags);
      console.log('[Inspector] onAddTags result:', result);
      
      if (tagInput) tagInput.value = '';
      
      if (!result?.applied) {
        setTagStatus('Тег уже есть');
      } else {
        setTagStatus('Теги добавлены');
      }
    } catch (error) {
      console.error('[Inspector] Error adding tags:', error);
      const message = error?.message || 'Не удалось добавить тег';
      setTagStatus(message, true);
    } finally {
      toggleTagForm(false);
    }
  };
  
  // Подключаем обработчик к форме
  if (tagForm) {
    tagForm.addEventListener('submit', handleTagSubmit);
    console.log('[Inspector] Tag form submit handler attached');
  }
  
  // Также подключаем к кнопке напрямую на случай если submit не срабатывает
  const tagButton = tagForm?.querySelector('button[type="submit"]');
  if (tagButton) {
    tagButton.addEventListener('click', (e) => {
      console.log('[Inspector] Tag button clicked');
      if (tagForm) {
        e.preventDefault();
        handleTagSubmit(e);
      }
    });
    console.log('[Inspector] Tag button click handler attached');
  }
  
  console.log('[Inspector] Tag handlers setup:', {
    form: !!tagForm,
    input: !!tagInput,
    status: !!tagStatus,
    button: !!tagButton,
    onAddTags: typeof options.onAddTags
  });
  
  // Тестовый клик-обработчик для отладки
  if (tagForm) {
    tagForm.addEventListener('click', (e) => {
      console.log('[Inspector] Form clicked:', e.target);
    });
  }

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
  
  async function ensureTagSuggestions() {
    if (tagsLoaded) return allTags;
    try {
      const res = await fetch('/api/tags');
      if (!res.ok) throw new Error('Failed to load tags');
      const data = await res.json();
      allTags = data.tags || [];
      tagsLoaded = true;
      console.log('[Inspector] Loaded tag suggestions:', allTags);
      populateTagSuggestions();
    } catch (error) {
      console.error('[Inspector] Error loading tags:', error);
    }
    return allTags;
  }
  
  function populateTagSuggestions() {
    if (!availableTagsEl) return;
    
    availableTagsEl.innerHTML = '';
    
    if (!allTags.length) {
      const empty = document.createElement('span');
      empty.className = 'muted';
      empty.textContent = 'Нет доступных тегов';
      availableTagsEl.appendChild(empty);
      return;
    }
    
    // Получаем текущие теги заметки
    const currentTags = new Set(noteState?.tags || []);
    
    allTags.forEach((tag) => {
      // Не показываем теги, которые уже добавлены к заметке
      if (currentTags.has(tag)) return;
      
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip chip--clickable';
      chip.textContent = tag;
      chip.addEventListener('click', async () => {
        console.log('[Inspector] Available tag clicked:', tag);
        if (typeof options.onAddTags === 'function') {
          try {
            await options.onAddTags([tag]);
          } catch (error) {
            console.error('[Inspector] Error adding tag:', error);
          }
        }
      });
      availableTagsEl.appendChild(chip);
    });
    
    console.log('[Inspector] Tag suggestions populated:', allTags.length);
  }
  
  let noteState = null;

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

  function toggleTagForm(disabled) {
    tagForm?.querySelectorAll('input, button').forEach((el) => {
      el.disabled = disabled;
    });
  }

  function setStatus(message, isError = false) {
    if (!linkStatus) return;
    linkStatus.textContent = message || '';
    linkStatus.classList.toggle('error', Boolean(isError && message));
  }

  function setTagStatus(message, isError = false) {
    if (!tagStatus) return;
    tagStatus.textContent = message || '';
    tagStatus.classList.toggle('error', Boolean(isError && message));
  }

  // Загружаем теги при инициализации
  ensureTagSuggestions();
  
  return {
    async onOpen(note) {
      currentNoteId = note?.id || null;
      await ensureNoteOptions();
      await ensureTagSuggestions();
      populateLinkOptions(note);
    },
    update(note) {
      console.log('[Inspector] Updating with note:', note);
      console.log('[Inspector] Tags:', note?.tags);
      
      noteState = note;
      currentNoteId = note?.id || null;
      renderTags(tagsEl, note?.tags || [], async (tag) => {
        // Удаляем тег
        if (typeof options.onRemoveTag === 'function') {
          await options.onRemoveTag(tag);
        }
      });
      renderLinks(linksEl, note?.linksFrom || [], note?.linksTo || []);
      renderProperties(propsEl, note?.passport || {}, note);
      const weight = clampWeight(note?.layoutHints?.sizeWeight, minWeight, maxWeight);
      syncSizeInputs(weight, { updateNumber: true, updateSlider: true });
      
      // Обновляем список доступных тегов (исключаем уже добавленные)
      populateTagSuggestions();
    },
  };
}

function renderTags(container, tags, onRemove) {
  console.log('[Inspector] renderTags called:', { container: !!container, tags });
  
  if (!container) {
    console.error('[Inspector] Tags container not found!');
    return;
  }
  
  container.innerHTML = '';
  
  if (!Array.isArray(tags) || tags.length === 0) {
    console.log('[Inspector] No tags to display');
    const empty = document.createElement('span');
    empty.className = 'muted';
    empty.textContent = 'Тегов пока нет';
    container.appendChild(empty);
    return;
  }
  
  console.log('[Inspector] Rendering', tags.length, 'tags');
  tags.forEach((tag) => {
    const chip = document.createElement('span');
    chip.className = 'chip chip--removable';
    
    const text = document.createElement('span');
    text.textContent = tag;
    chip.appendChild(text);
    
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'chip__remove';
    removeBtn.textContent = '×';
    removeBtn.setAttribute('aria-label', `Удалить тег ${tag}`);
    removeBtn.addEventListener('click', async () => {
      console.log('[Inspector] Remove tag clicked:', tag);
      if (typeof onRemove === 'function') {
        await onRemove(tag);
      }
    });
    chip.appendChild(removeBtn);
    
    container.appendChild(chip);
  });
}

function normalizeTags(raw) {
  if (!raw) return [];
  const parts = raw.split(/[\n,;]+/g);
  const cleaned = parts
    .map((tag) => tag.trim().replace(/^#+/, ''))
    .filter(Boolean);
  return Array.from(new Set(cleaned));
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

function renderProperties(container, passport, note = {}) {
  if (!container) return;
  container.innerHTML = '';
  const entries = [
    ['createdAt', note?.createdAt || note?.created_at],
    ['updatedAt', note?.updatedAt || note?.updated_at],
    ...Object.entries(passport || {}),
  ].filter(([, value]) => value !== undefined && value !== null && value !== '');

  entries.forEach(([key, value]) => {
    const dt = document.createElement('dt');
    dt.textContent = formatPropertyLabel(key);
    const dd = document.createElement('dd');
    dd.textContent = formatValue(value);
    container.append(dt, dd);
  });
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (value && typeof value === 'object') return JSON.stringify(value, null, 2);
  if (typeof value === 'string' && looksLikeDate(value)) {
    return formatDateTime(value);
  }
  return String(value ?? '');
}

function formatPropertyLabel(key) {
  const labels = {
    createdAt: 'Создана',
    created_at: 'Создана',
    updatedAt: 'Обновлена',
    updated_at: 'Обновлена',
  };
  return labels[key] || String(key)
    .replace(/[_-]+/g, ' ')
    .replace(/([a-zа-я])([A-ZА-Я])/g, '$1 $2');
}

function looksLikeDate(value) {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function clampWeight(value, min, max) {
  const numeric = Number.parseFloat(value);
  if (Number.isNaN(numeric)) {
    const fallback = Math.max(min, Math.min(max, 1));
    return fallback;
  }
  return Math.max(min, Math.min(max, numeric));
}
