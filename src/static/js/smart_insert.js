const URL_REGEX = /(https?:\/\/[^\s]+)/i;
const YOUTUBE_HOST_RE = /(youtu\.be|youtube\.com|youtube-nocookie\.com)/i;
const INSTAGRAM_HOSTS = new Set(['instagram.com', 'www.instagram.com']);
const TIKTOK_HOSTS = new Set(['tiktok.com', 'www.tiktok.com', 'vt.tiktok.com', 'vm.tiktok.com']);
const INSTAGRAM_REEL_RE = /^[A-Za-z0-9_-]+$/;
const TIKTOK_VIDEO_RE = /^\d+$/;

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

    const instagramUrl = normalizeInstagramReelUrl(url);
    if (instagramUrl) {
      onTransform(blockId, { type: 'instagram', data: { url: instagramUrl } });
      return;
    }

    const tiktokInfo = normalizeTikTokUrl(url);
    if (tiktokInfo) {
      if (tiktokInfo.needsResolve) {
        // Short URL - needs backend resolve
        try {
          const res = await fetch('/api/resolve/tiktok', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
          });
          if (res.ok) {
            const payload = await res.json();
            if (payload?.videoId) {
              onTransform(blockId, { type: 'tiktok', data: { url: payload.url || url, videoId: payload.videoId } });
              return;
            }
          }
        } catch (error) {
          console.warn('TikTok resolve failed', error);
        }
      } else {
        onTransform(blockId, { type: 'tiktok', data: { url: tiktokInfo.url, videoId: tiktokInfo.videoId } });
        return;
      }
    }

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

function safeParseUrl(rawUrl) {
  if (!rawUrl) return null;
  try {
    return new URL(rawUrl.trim());
  } catch (error) {
    return null;
  }
}

function normalizeInstagramReelUrl(rawUrl) {
  const parsed = safeParseUrl(rawUrl);
  if (!parsed) return '';
  if (!INSTAGRAM_HOSTS.has(parsed.host.toLowerCase())) return '';
  const segments = parsed.pathname.split('/').filter(Boolean);
  if (segments.length < 2 || segments[0] !== 'reel') return '';
  const code = segments[1];
  if (!INSTAGRAM_REEL_RE.test(code)) return '';
  return `https://www.instagram.com/reel/${code}/`;
}

function normalizeTikTokUrl(rawUrl) {
  const parsed = safeParseUrl(rawUrl);
  if (!parsed) return null;
  const host = parsed.host.toLowerCase();
  if (!TIKTOK_HOSTS.has(host)) return null;
  
  // Short URL format (vt.tiktok.com, vm.tiktok.com)
  if (host === 'vt.tiktok.com' || host === 'vm.tiktok.com') {
    return { url: rawUrl, videoId: null, needsResolve: true };
  }
  
  // Full URL format: /@user/video/1234567890
  const segments = parsed.pathname.split('/').filter(Boolean);
  if (segments.length < 3 || segments[1] !== 'video') return null;
  const videoId = segments[2];
  if (!TIKTOK_VIDEO_RE.test(videoId)) return null;
  return { url: `${parsed.origin}${parsed.pathname}`, videoId, needsResolve: false };
}
