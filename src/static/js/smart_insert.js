const URL_REGEX = /(https?:\/\/[^\s]+)/i;
const YOUTUBE_HOST_RE = /(youtu\.be|youtube\.com|youtube-nocookie\.com)/i;

export function initSmartInsert(canvas, { onTransform }) {
  if (!canvas || typeof onTransform !== 'function') return;

  canvas.addEventListener('input', async (event) => {
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
    if (!urlMatch) return;

    const url = urlMatch[0];

    if (YOUTUBE_HOST_RE.test(url)) {
      try {
        const res = await fetch('/api/resolve/youtube', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        if (!res.ok) {
          throw new Error(await res.text());
        }
        const payload = await res.json();
        if (payload?.block) {
          onTransform(blockId, { type: payload.block.type, data: payload.block.data });
          return;
        }
      } catch (error) {
        console.warn('YouTube resolve failed', error);
      }
    }

  });
}
