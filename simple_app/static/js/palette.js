import { uuid } from './utils.js';

export function initPalette({ paletteEl, triggerEl, onInsert }) {
  if (!paletteEl || !triggerEl) return;

  const close = () => paletteEl.setAttribute('aria-hidden', 'true');
  const open = () => paletteEl.setAttribute('aria-hidden', 'false');

  triggerEl.addEventListener('click', (event) => {
    event.preventDefault();
    const isHidden = paletteEl.getAttribute('aria-hidden') !== 'false';
    if (isHidden) {
      open();
    } else {
      close();
    }
  });

  paletteEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-block]');
    if (!button) return;
    const blockType = button.dataset.block;
    const payload = buildBlock(blockType, button.dataset);
    if (payload && typeof onInsert === 'function') {
      onInsert(payload);
    }
    close();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });
}

function buildBlock(type, dataset = {}) {
  const id = uuid();
  switch (type) {
    case 'heading':
      return { id, type: 'heading', data: { level: parseInt(dataset.level || '1', 10), text: 'Новый заголовок' } };
    case 'paragraph':
      return { id, type: 'paragraph', data: { parts: [{ text: 'Новый абзац' }] } };
    case 'bulletList':
      return { id, type: 'bulletList', data: { items: [{ text: 'Первый пункт' }] } };
    case 'quote':
      return { id, type: 'quote', data: { text: 'Цитата', cite: '' } };
    case 'table':
      return { id, type: 'table', data: { rows: [['', ''], ['', '']] } };
    case 'image':
      return { id, type: 'image', data: { src: '', alt: '', caption: '' } };
    case 'source':
      return {
        id,
        type: 'source',
        data: { url: '', title: 'Источник', domain: '', published_at: null, summary: '' },
      };
    case 'todo':
      return { id, type: 'todo', data: { items: [{ id: uuid(), text: 'Задача', done: false }] } };
    case 'summary':
      return { id, type: 'summary', data: { dateISO: new Date().toISOString().split('T')[0], text: 'Краткая сводка' } };
    case 'divider':
      return { id, type: 'divider', data: {} };
    default:
      return null;
  }
}
