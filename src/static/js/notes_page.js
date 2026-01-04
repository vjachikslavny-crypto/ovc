import { renderNoteCard } from './notes_renderer.js';

const limit = 20;
let offset = 0;
let notesCache = [];

document.addEventListener('DOMContentLoaded', () => {
  const listEl = document.getElementById('notes-list');
  const searchEl = document.getElementById('notes-search');
  const createBtn = document.getElementById('create-note');
  const loadMoreBtn = document.getElementById('load-more');

  if (!listEl) return;

  const state = {
    loading: false,
    reachedEnd: false,
  };

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

  function renderList() {
    const query = (searchEl?.value || '').trim().toLowerCase();
    listEl.innerHTML = '';
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
      listEl.appendChild(renderNoteCard(note));
    });
  }

  searchEl?.addEventListener('input', () => renderList());

  loadMoreBtn?.addEventListener('click', () => fetchNotes());

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
