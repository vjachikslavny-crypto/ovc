const URL_REGEX = /(https?:\/\/[^\s]+)/i;

export function initSmartInsert(canvas, { onTransform }) {
  if (!canvas || typeof onTransform !== 'function') return;

  canvas.addEventListener('input', (event) => {
    const blockEl = event.target.closest('[data-block-id]');
    if (!blockEl) return;
    const blockId = blockEl.dataset.blockId;
    const text = blockEl.innerText.trim();
    const type = blockEl.dataset.blockType;

    if (type === 'paragraph' && text.startsWith('- ')) {
      const items = text
        .split('\n')
        .map((line) => line.replace(/^-\s*/, '').trim())
        .filter(Boolean)
        .map((value) => ({ text: value }));
      onTransform(blockId, { type: 'bulletList', data: { items } });
      return;
    }

    if (type === 'paragraph' && text.toLowerCase().startsWith('сводка:')) {
      const body = text.replace(/^сводка:/i, '').trim();
      const today = new Date().toISOString().split('T')[0];
      onTransform(blockId, { type: 'summary', data: { dateISO: today, text: body } });
      return;
    }

    const urlMatch = text.match(URL_REGEX);
    if (urlMatch && confirm('Оформить как источник?')) {
      let domain = '';
      try {
        domain = new URL(urlMatch[0]).hostname;
      } catch (error) {
        domain = '';
      }
      onTransform(blockId, {
        type: 'source',
        data: {
          url: urlMatch[0],
          title: text.replace(urlMatch[0], '').trim() || 'Источник',
          domain,
          published_at: null,
          summary: '',
        },
      });
    }
  });
}
