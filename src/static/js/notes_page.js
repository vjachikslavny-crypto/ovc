import { renderNoteCard } from './notes_renderer.js';

const limit = 20;
let offset = 0;
let notesCache = [];
let deepSearchResults = null;

document.addEventListener('DOMContentLoaded', () => {
  const listEl = document.getElementById('notes-list');
  const searchEl = document.getElementById('notes-search');
  const createBtn = document.getElementById('create-note');
  const loadMoreBtn = document.getElementById('load-more');

  const deepToggle = document.getElementById('deep-search-toggle');
  const deepPanel = document.getElementById('deep-search-panel');
  const deepInput = document.getElementById('deep-search-input');
  const deepGoBtn = document.getElementById('deep-search-go');
  const deepCloseBtn = document.getElementById('deep-search-close');
  const deepStatus = document.getElementById('deep-search-status');

  if (!listEl) return;

  const state = {
    loading: false,
    reachedEnd: false,
  };

  /* ── Regular notes loading ── */

  async function fetchNotes(reset = false) {
    if (state.loading || state.reachedEnd) return;
    state.loading = true;
    loadMoreBtn?.setAttribute('disabled', 'disabled');
    const currentOffset = reset ? 0 : offset;
    if (reset) {
      offset = 0;
      state.reachedEnd = false;
    }
    try {
      const res = await fetch(`/api/notes?limit=${limit}&offset=${currentOffset}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (reset) {
        notesCache = data.items;
      } else {
        notesCache = notesCache.concat(data.items);
      }
      offset = currentOffset + data.items.length;
      state.reachedEnd = offset >= data.total;
      renderList();
    } catch (error) {
      console.error('Failed to load notes', error);
    } finally {
      state.loading = false;
      if (!state.reachedEnd) {
        loadMoreBtn?.removeAttribute('disabled');
      }
      if (state.reachedEnd) {
        loadMoreBtn?.setAttribute('disabled', 'disabled');
      }
    }
  }

  /* ── Render ── */

  function renderList() {
    listEl.innerHTML = '';
    const onNoteDeleted = (noteId) => {
      notesCache = notesCache.filter((note) => note.id !== noteId);
      if (deepSearchResults) {
        deepSearchResults.items = deepSearchResults.items.filter((note) => note.id !== noteId);
      }
      renderList();
    };

    if (deepSearchResults) {
      const info = document.createElement('div');
      info.className = 'deep-search-panel__status';
      info.style.marginBottom = '12px';
      info.textContent = `Глубокий поиск: «${deepSearchResults.query}» — найдено ${deepSearchResults.items.length}`;
      listEl.appendChild(info);

      if (deepSearchResults.items.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'notes-empty';
        empty.textContent = 'Ничего не найдено. Попробуйте другой запрос.';
        listEl.appendChild(empty);
        return;
      }
      deepSearchResults.items.forEach((note) => {
        listEl.appendChild(renderNoteCard(note, { onDeleted: onNoteDeleted }));
      });
      return;
    }

    const query = (searchEl?.value || '').trim().toLowerCase();
    const filtered = query
      ? notesCache.filter((note) =>
          note.title.toLowerCase().includes(query) ||
          (note.styleTheme || '').toLowerCase().includes(query)
        )
      : notesCache;

    if (filtered.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'notes-empty';
      empty.textContent = 'Заметок пока нет. Нажмите «Новая», чтобы создать первую.';
      listEl.appendChild(empty);
      return;
    }

    filtered.forEach((note) => {
      listEl.appendChild(renderNoteCard(note, { onDeleted: onNoteDeleted }));
    });
  }

  searchEl?.addEventListener('input', () => {
    if (deepSearchResults) {
      deepSearchResults = null;
      if (deepStatus) deepStatus.textContent = '';
    }
    renderList();
  });

  loadMoreBtn?.addEventListener('click', () => fetchNotes());

  /* ── Deep search panel ── */

  function openDeepPanel() {
    deepPanel.hidden = false;
    deepToggle.classList.add('active');
    deepInput.focus();
  }

  function closeDeepPanel() {
    deepPanel.hidden = true;
    deepToggle.classList.remove('active');
    deepInput.value = '';
    if (deepStatus) deepStatus.textContent = '';
    if (deepSearchResults) {
      deepSearchResults = null;
      loadMoreBtn?.style.removeProperty('display');
      renderList();
    }
  }

  async function performDeepSearch() {
    const query = (deepInput?.value || '').trim();
    if (!query) {
      deepInput?.focus();
      return;
    }

    deepGoBtn.setAttribute('disabled', 'disabled');
    deepGoBtn.textContent = 'Ищу…';
    if (deepStatus) deepStatus.textContent = 'Поиск по содержимому заметок и файлам…';

    try {
      const res = await fetch(`/api/notes/search/full?q=${encodeURIComponent(query)}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      deepSearchResults = { items: data.items, query, total: data.total };
      loadMoreBtn?.style.setProperty('display', 'none');
      if (deepStatus) deepStatus.textContent = `Найдено: ${data.items.length}`;
      renderList();
    } catch (error) {
      console.error('Deep search failed', error);
      if (deepStatus) deepStatus.textContent = 'Ошибка поиска. Попробуйте ещё раз.';
    } finally {
      deepGoBtn.removeAttribute('disabled');
      deepGoBtn.textContent = 'Найти';
    }
  }

  deepToggle?.addEventListener('click', () => {
    if (deepPanel.hidden) {
      openDeepPanel();
    } else {
      closeDeepPanel();
    }
  });

  deepCloseBtn?.addEventListener('click', closeDeepPanel);

  deepGoBtn?.addEventListener('click', performDeepSearch);

  deepInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      performDeepSearch();
    }
    if (e.key === 'Escape') {
      closeDeepPanel();
    }
  });

  /* ── Create note ── */

  createBtn?.addEventListener('click', async () => {
    createBtn.setAttribute('disabled', 'disabled');
    try {
      const res = await fetch('/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Новая заметка',
          blocks: [],
          styleTheme: document.body.dataset.theme || 'clean',
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const note = await res.json();
      window.location.href = `/notes/${note.id}`;
    } catch (error) {
      console.error('Failed to create note', error);
    } finally {
      createBtn.removeAttribute('disabled');
    }
  });

  fetchNotes(true);
});
