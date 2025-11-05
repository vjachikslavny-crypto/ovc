import { renderNote } from './blocks_render.js';
import { initToolbar } from './toolbar.js';
import { initInlineBubble } from './inline_bubble.js';
import { initPalette } from './palette.js';
import { initSmartInsert } from './smart_insert.js';
import { initInspector } from './inspector.js';
import { initHints } from './hints.js';
import { uuid } from './utils.js';

const SAVE_DEBOUNCE = 600;

document.addEventListener('DOMContentLoaded', () => {
  const editorEl = document.querySelector('.editor');
  if (!editorEl) return;

  const canvas = document.getElementById('note-blocks');
  const titleEl = document.getElementById('note-title');
  const shareBtn = document.getElementById('note-share');
  const backBtn = document.getElementById('nav-back');
  const infoBtn = document.getElementById('note-info');
  const paletteEl = document.getElementById('block-palette');
  const fabPlus = document.getElementById('fab-plus');
  const fabVoice = document.getElementById('fab-voice');
  const fabAttach = document.getElementById('fab-attach');
  const fileInput = document.getElementById('file-input');
  const toolbarEl = document.getElementById('format-toolbar');
  const bubbleEl = document.getElementById('inline-bubble');
  const inspectorEl = document.getElementById('note-inspector');
  const hintBanner = document.getElementById('hint-banner');
  const hintText = document.getElementById('hint-text');
  const hintDismiss = document.getElementById('hint-dismiss');
  const llmToggle = document.getElementById('llm-toggle');

  const inspector = initInspector(inspectorEl);
  const hints = initHints(hintBanner, hintText, hintDismiss);

  initToolbar(toolbarEl);
  initInlineBubble(bubbleEl, canvas);
  initPalette({ paletteEl, triggerEl: fabPlus, onInsert: handleInsertBlock });
  initSmartInsert(canvas, { onTransform: handleTransformBlock });

  let noteState = {
    id: editorEl.dataset.noteId || '',
    title: 'Без названия',
    styleTheme: document.body.dataset.theme || 'clean',
    blocks: [],
    layoutHints: {},
    passport: {},
    tags: [],
    linksFrom: [],
    linksTo: [],
    sources: [],
  };
  let saveTimer = null;
  let focusedBlockId = null;

  const saveQueue = [];

  async function ensureNote() {
    if (noteState.id) return noteState.id;
    const res = await fetch('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Новая заметка',
        blocks: [],
        styleTheme: noteState.styleTheme,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const note = await res.json();
    noteState.id = note.id;
    window.history.replaceState({}, '', `/notes/${note.id}`);
    return note.id;
  }

  async function loadNote() {
    const noteId = await ensureNote();
    const res = await fetch(`/api/notes/${noteId}`);
    if (!res.ok) throw new Error(await res.text());
    const note = await res.json();
    noteState = {
      ...noteState,
      id: note.id,
      title: note.title,
      styleTheme: note.styleTheme,
      layoutHints: note.layoutHints ?? {},
      passport: note.passport ?? {},
      blocks: Array.isArray(note.blocks) ? note.blocks : [],
      tags: note.tags || [],
      linksFrom: note.linksFrom || [],
      linksTo: note.linksTo || [],
      sources: note.sources || [],
    };
    render();
    if (llmToggle) {
      llmToggle.checked = Boolean(noteState.layoutHints?.autoLLM);
    }
    hints.push('Нажмите ＋, чтобы добавить новый блок.');
  }

  function render() {
    titleEl.textContent = noteState.title || 'Без названия';
    renderNote(canvas, noteState, document.body.dataset.theme || 'clean');
    hydrateBlocks();
    inspector.update(noteState);
    if (focusedBlockId) {
      const focusedEl = canvas.querySelector(`[data-block-id="${focusedBlockId}"]`);
      focusedEl?.focus();
    }
  }

  function hydrateBlocks() {
    canvas.querySelectorAll('[data-block-id]').forEach((blockEl) => {
      blockEl.addEventListener('focus', () => {
        focusedBlockId = blockEl.dataset.blockId;
      });
      blockEl.addEventListener('input', () => {
        updateBlockFromDom(blockEl);
        scheduleSave();
      });
    });
  }

  function updateBlockFromDom(blockEl) {
    const blockId = blockEl.dataset.blockId;
    const blockType = blockEl.dataset.blockType;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block) return;

    switch (blockType) {
      case 'heading':
        block.data.text = blockEl.textContent.trim();
        break;
      case 'paragraph':
        block.data.parts = [{ text: blockEl.textContent }];
        break;
      case 'bulletList':
      case 'numberList':
        block.data.items = Array.from(blockEl.querySelectorAll('li')).map((li) => ({ text: li.textContent.trim() }));
        break;
      case 'quote':
        block.data.text = blockEl.textContent.trim();
        break;
      case 'summary':
        block.data.text = blockEl.innerText.replace(/Сводка ·.+\n?/i, '').trim();
        break;
      case 'todo':
        block.data.items = Array.from(blockEl.querySelectorAll('li')).map((li, index) => ({
          id: block.data.items?.[index]?.id || uuid(),
          text: li.textContent.trim(),
          done: block.data.items?.[index]?.done || false,
        }));
        break;
      default:
        break;
    }
  }

  function handleInsertBlock(block) {
    if (!block) return;
    const blocks = noteState.blocks.slice();
    if (focusedBlockId) {
      const index = blocks.findIndex((item) => item.id === focusedBlockId);
      if (index >= 0) {
        blocks.splice(index + 1, 0, block);
      } else {
        blocks.push(block);
      }
    } else {
      blocks.push(block);
    }
    noteState.blocks = blocks;
    focusedBlockId = block.id;
    hints.push('Выделите текст, чтобы появилось форматирование.');
    render();
    scheduleSave();
  }

  function handleTransformBlock(blockId, nextData) {
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block) return;
    block.type = nextData.type;
    block.data = nextData.data;
    focusedBlockId = blockId;
    render();
    scheduleSave();
  }

  function scheduleSave() {
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(persistNote, SAVE_DEBOUNCE);
  }

  async function persistNote() {
    saveTimer = null;
    const payload = {
      title: noteState.title,
      blocks: noteState.blocks,
      styleTheme: noteState.styleTheme,
      layoutHints: noteState.layoutHints,
      passport: noteState.passport,
    };
    saveQueue.push(payload);
    if (saveQueue.length > 1) return; // already saving

    while (saveQueue.length) {
      const next = saveQueue[0];
      try {
        await fetch(`/api/notes/${noteState.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(next),
        });
      } catch (error) {
        console.error('Failed to save note', error);
      } finally {
        saveQueue.shift();
      }
    }
  }

  titleEl.addEventListener('input', () => {
    noteState.title = titleEl.textContent.trim();
    scheduleSave();
  });

  document.addEventListener('theme-change', (event) => {
    noteState.styleTheme = event.detail?.theme || 'clean';
    render();
    scheduleSave();
  });

  llmToggle?.addEventListener('change', () => {
    noteState.layoutHints = {
      ...noteState.layoutHints,
      autoLLM: llmToggle.checked,
    };
    scheduleSave();
  });

  shareBtn?.addEventListener('click', async () => {
    const choice = prompt('Введите формат экспорта: pdf или docx', 'pdf');
    if (!choice) return;
    if (choice.toLowerCase() === 'docx') {
      window.open(`/api/export/docx/${noteState.id}`, '_blank');
    } else {
      window.print();
    }
  });
  backBtn?.addEventListener('click', () => (window.location.href = '/notes'));

  infoBtn?.addEventListener('click', () => {
    const hidden = inspectorEl.getAttribute('aria-hidden') !== 'false';
    inspectorEl.setAttribute('aria-hidden', hidden ? 'false' : 'true');
  });

  fabVoice?.addEventListener('click', async () => {
    const text = prompt('Продиктуйте заметку (ввод текстом)');
    if (!text) return;
    handleInsertBlock({
      id: uuid(),
      type: 'paragraph',
      data: { parts: [{ text }] },
    });
  });

  fabAttach?.addEventListener('click', () => fileInput?.click());

  fileInput?.addEventListener('change', (event) => {
    const files = Array.from(event.target.files || []);
    files.forEach((file) => {
      const url = URL.createObjectURL(file);
      handleInsertBlock({
        id: uuid(),
        type: 'image',
        data: { src: url, alt: file.name, caption: '' },
      });
    });
    fileInput.value = '';
  });

  loadNote().catch((error) => console.error('Unable to load note', error));
});
