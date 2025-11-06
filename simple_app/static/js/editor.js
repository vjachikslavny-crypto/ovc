import { renderNote } from './blocks_render.js';
import { initToolbar, clearSelectionSnapshot, rememberSelection } from './toolbar.js';
import { initInlineBubble } from './inline_bubble.js';
import { initPalette } from './palette.js';
import { initSmartInsert } from './smart_insert.js';
import { initInspector } from './inspector.js';
import { initHints } from './hints.js';
import { uuid } from './utils.js';

const SAVE_DEBOUNCE = 600;
const PLACEHOLDER_STRINGS = new Set(['Новый заголовок', 'Новый абзац']);

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

  const hints = initHints(hintBanner, hintText, hintDismiss);
  const inspector = initInspector(inspectorEl, {
    onSetLayoutHint: handleLayoutHintUpdate,
    fetchNoteOptions: fetchLinkableNotes,
    onCreateLink: createManualLink,
  });

  initToolbar(toolbarEl, canvas);
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
  let canvasClickBound = false;
  let pendingCaretBlockId = null;

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

  async function fetchNoteDetail(noteId) {
    const res = await fetch(`/api/notes/${noteId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function applyNote(note) {
    noteState = {
      ...noteState,
      id: note.id,
      title: note.title,
      styleTheme: note.styleTheme,
      layoutHints: note.layoutHints ?? {},
      passport: note.passport ?? {},
      blocks: cleanIncomingBlocks(note.blocks),
      tags: note.tags || [],
      linksFrom: note.linksFrom || [],
      linksTo: note.linksTo || [],
      sources: note.sources || [],
    };
    focusedBlockId = null;
    render();
  }

  async function refreshNoteState() {
    if (!noteState.id) return;
    const note = await fetchNoteDetail(noteState.id);
    applyNote(note);
  }

  async function loadNote() {
    const noteId = await ensureNote();
    const note = await fetchNoteDetail(noteId);
    applyNote(note);
    hints.push('Нажмите ＋, чтобы добавить новый блок.');
  }

  function render() {
    titleEl.textContent = noteState.title || 'Без названия';
    renderNote(canvas, noteState, document.body.dataset.theme || 'clean');
    clearSelectionSnapshot();
    hydrateBlocks();
    inspector.update(noteState);
    if (llmToggle) {
      llmToggle.checked = Boolean(noteState.layoutHints?.autoLLM);
    }
    if (pendingCaretBlockId) {
      const pendingEl = canvas.querySelector(`[data-block-id="${pendingCaretBlockId}"]`);
      if (pendingEl) {
        const editable = getEditableElement(pendingEl) || pendingEl;
        placeCaretAtEnd(editable);
      }
      pendingCaretBlockId = null;
    }
  }

  function hydrateBlocks() {
    canvas.querySelectorAll('[data-block-id]').forEach((blockEl) => {
      const editableEl = getEditableElement(blockEl);
      if (editableEl) {
        editableEl.classList.add('note-editable');
        if (!blockEl.dataset.editableBound) {
          blockEl.dataset.editableBound = 'true';
          blockEl.addEventListener('click', (event) => {
            if (event.target === editableEl || editableEl.contains(event.target)) {
              return;
            }
            focusEditable(editableEl);
          });
        }
      }
      applyPlaceholderState(blockEl);
      blockEl.addEventListener('focus', () => {
        focusedBlockId = blockEl.dataset.blockId;
        pendingCaretBlockId = null;
      });
      blockEl.addEventListener('mousedown', () => {
        pendingCaretBlockId = null;
      });
      blockEl.addEventListener('mouseup', () => {
        if (editableEl) {
          requestAnimationFrame(() => {
            if (document.activeElement === editableEl || editableEl.contains(document.activeElement)) {
              return;
            }
            const selection = window.getSelection();
            if (selection && editableEl.contains(selection.anchorNode)) {
              editableEl.focus({ preventScroll: false });
              return;
            }
            focusEditable(editableEl);
          });
        }
        rememberSelection();
      });
      blockEl.addEventListener('keyup', () => {
        rememberSelection();
      });
      blockEl.addEventListener('input', () => {
        updateBlockFromDom(blockEl);
        applyPlaceholderState(blockEl);
        scheduleSave();
        rememberSelection();
      });
    });

    if (!canvasClickBound) {
      canvas.addEventListener('click', onCanvasBlankClick);
      canvasClickBound = true;
    }
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
      case 'paragraph': {
        const parts = extractRichTextParts(blockEl);
        block.data.parts = parts;
        break;
      }
      case 'bulletList':
      case 'numberList':
        block.data.items = Array.from(blockEl.querySelectorAll('li')).map((li) => ({
          text: li.textContent.trim(),
        }));
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
    applyPlaceholderState(blockEl);
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
    pendingCaretBlockId = block.id;
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
    pendingCaretBlockId = blockId;
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
    if (hidden) {
      inspector.onOpen?.(noteState);
    }
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

  function handleLayoutHintUpdate(key, rawValue) {
    const numeric = Number.parseFloat(rawValue);
    const value = Number.isNaN(numeric) ? rawValue : Math.max(0.3, Math.min(6, numeric));
    noteState.layoutHints = {
      ...noteState.layoutHints,
      [key]: value,
    };
    scheduleSave();
  }

  async function fetchLinkableNotes() {
    const res = await fetch('/api/notes?limit=100');
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    if (!Array.isArray(data?.items)) return [];
    return data.items.map((item) => ({ id: item.id, title: item.title }));
  }

  async function createManualLink({ toId, reason }) {
    const noteId = await ensureNote();
    if (!toId) throw new Error('Не выбрана цель связи');
    if (toId === noteId) throw new Error('Нельзя связать заметку саму с собой');
    const normalizedReason = (reason || '').trim() || 'manual';
    const payload = {
      draft: [
        {
          type: 'add_link',
          noteId,
          fromId: noteId,
          toId,
          reason: normalizedReason,
          confidence: 0.9,
        },
      ],
    };
    const res = await fetch('/api/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const result = await res.json();
    if (!result.applied) {
      throw new Error('Связь уже существует');
    }
    await refreshNoteState();
  }

  function onCanvasBlankClick(event) {
    if (event.button !== 0) return;
    if (event.target.closest('[data-block-id]')) return;
    focusTailBlock();
  }

  function focusTailBlock() {
    const lastBlock = canvas.querySelector('[data-block-id]:last-of-type');
    if (lastBlock) {
      const editable = getEditableElement(lastBlock);
      if (editable) {
        focusedBlockId = lastBlock.dataset.blockId;
        placeCaretAtEnd(editable);
        return;
      }
    }
    const fallback = {
      id: uuid(),
      type: 'paragraph',
      data: { parts: [{ text: '' }] },
    };
    const nextBlocks = Array.isArray(noteState.blocks) ? noteState.blocks.slice() : [];
    nextBlocks.push(fallback);
    noteState.blocks = nextBlocks;
    focusedBlockId = fallback.id;
    pendingCaretBlockId = fallback.id;

    render();
    scheduleSave();
  }

  function focusEditable(element) {
    if (!element) return;
    if (document.activeElement !== element) {
      element.focus({ preventScroll: false });
    }
    const selection = window.getSelection();
    if (!selection) return;
    if (element.contains(selection.anchorNode) && element.contains(selection.focusNode)) {
      return;
    }
    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function getEditableElement(blockEl) {
    if (!blockEl) return null;
    if (blockEl instanceof HTMLElement && blockEl.isContentEditable) {
      return blockEl;
    }
    return blockEl.querySelector('.note-editable[contenteditable="true"]') || blockEl.querySelector('[contenteditable="true"]');
  }

  function placeCaretAtEnd(element) {
    if (!element) return;
    const target = element;
    if (typeof target.focus === 'function') {
      target.focus({ preventScroll: true });
    }
    const selection = window.getSelection();
    if (!selection) return;
    const range = document.createRange();
    let focusTarget = target;
    if (target.matches('ul, ol')) {
      const lastItem = target.querySelector('li:last-child');
      if (lastItem) {
        focusTarget = lastItem;
      }
    }
    range.selectNodeContents(focusTarget);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
    rememberSelection();
  }

  function restorePendingCaret() {
    if (!pendingCaretBlockId) return;
    const element = canvas.querySelector(`[data-block-id="${pendingCaretBlockId}"]`);
    if (element) {
      const editable = getEditableElement(element) || element;
      placeCaretAtEnd(editable);
    }
    pendingCaretBlockId = null;
  }

  function stripPlaceholder(value, allowPlaceholderCheck = false) {
    if (value === null || value === undefined) return '';
    const stringValue = typeof value === 'string' ? value : String(value);
    const trimmed = stringValue.trim();
    if (!trimmed) return '';
    if (allowPlaceholderCheck && PLACEHOLDER_STRINGS.has(trimmed)) {
      return '';
    }
    return stringValue;
  }

  function cleanIncomingBlocks(blocks) {
    if (!Array.isArray(blocks)) return [];
    return blocks.map((block) => {
      if (!block || typeof block !== 'object') return block;
      const data = { ...(block.data || {}) };
      if (block.type === 'heading') {
        data.text = stripPlaceholder(data.text || '', true);
        return { ...block, data };
      }
      if (block.type === 'paragraph') {
        const rawParts = Array.isArray(data.parts)
          ? data.parts
          : [{ text: data.text || '' }];
        const parts = rawParts
          .map((part) => ({
            text: stripPlaceholder(part?.text || '', true),
            annotations: sanitizeAnnotations(part?.annotations),
          }))
          .filter((part) => part.text !== '');
        data.parts = parts.length ? parts : [{ text: '' }];
        delete data.text;
        return { ...block, data };
      }
      return { ...block, data };
    });
  }

  function sanitizeAnnotations(annotations) {
    if (!annotations || typeof annotations !== 'object') return undefined;
    const clean = {};
    if (annotations.bold) clean.bold = true;
    if (annotations.italic) clean.italic = true;
    if (annotations.underline) clean.underline = true;
    if (annotations.strike) clean.strike = true;
    if (annotations.code) clean.code = true;
    if (annotations.href) clean.href = String(annotations.href);
    return Object.keys(clean).length ? clean : undefined;
  }

  function extractRichTextParts(blockEl) {
    const segments = [];

    const walk = (node, marks) => {
      if (!node) return;
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent ?? '';
        if (text.length === 0) return;
        segments.push({
          text,
          annotations: Object.keys(marks).length ? { ...marks } : undefined,
        });
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;

      if (node.tagName?.toLowerCase() === 'br') {
        if (segments.length === 0 || segments[segments.length - 1].text !== '\n') {
          segments.push({
            text: '\n',
            annotations: Object.keys(marks).length ? { ...marks } : undefined,
          });
        } else {
          segments[segments.length - 1].text += '\n';
        }
        return;
      }

      const nextMarks = accumulateMarks(node, marks);
      node.childNodes.forEach((child) => walk(child, nextMarks));
    };

    blockEl.childNodes.forEach((child) => walk(child, {}));

    const merged = mergeSegments(segments).map((part) =>
      part.annotations ? part : { text: part.text }
    );
    return merged.length ? merged : [{ text: '' }];
  }

  function accumulateMarks(element, marks) {
    const tag = element.tagName?.toLowerCase?.() || '';
    const next = { ...marks };
    if (tag === 'b' || tag === 'strong') next.bold = true;
    if (tag === 'i' || tag === 'em') next.italic = true;
    if (tag === 'u') next.underline = true;
    if (tag === 's' || tag === 'del' || tag === 'strike') next.strike = true;
    if (tag === 'code') next.code = true;
    if (tag === 'a' && element.getAttribute) {
      const href = element.getAttribute('href');
      if (href) next.href = href;
    }

    const style = element.getAttribute?.('style') || '';
    if (style) {
      const lower = style.toLowerCase();
      if (lower.includes('font-weight') && !next.bold) {
        const match = lower.match(/font-weight\s*:\s*([^;]+)/);
        if (match && parseInt(match[1], 10) >= 500) next.bold = true;
      }
      if (lower.includes('font-style') && !next.italic) {
        if (lower.includes('italic')) next.italic = true;
      }
      if (lower.includes('text-decoration')) {
        if (lower.includes('underline')) next.underline = true;
        if (lower.includes('line-through')) next.strike = true;
      }
    }
    return next;
  }

  function mergeSegments(segments) {
    if (!segments.length) return segments;
    const merged = [];
    segments.forEach((segment) => {
      const prev = merged[merged.length - 1];
      if (
        prev &&
        shallowEqualAnnotations(prev.annotations, segment.annotations)
      ) {
        prev.text += segment.text;
      } else {
        merged.push({
          text: segment.text,
          annotations: segment.annotations,
        });
      }
    });
    return merged;
  }

  function shallowEqualAnnotations(a, b) {
    if (!a && !b) return true;
    if (!a || !b) return false;
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    return keysA.every((key) => Boolean(a[key]) === Boolean(b[key]));
  }

  loadNote().catch((error) => console.error('Unable to load note', error));

  function applyPlaceholderState(blockEl) {
    if (!blockEl || !blockEl.dataset) return;
    if (!blockEl.dataset.placeholder) return;
    const text = (blockEl.textContent || '').replace(/\u200B/g, '').trim();
    if (text.length === 0) {
      blockEl.dataset.empty = 'true';
    } else {
      delete blockEl.dataset.empty;
    }
  }
});
