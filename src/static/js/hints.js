const MAX_HINTS = 3;
const STORAGE_KEY = 'ovc-hints-shown';

export function initHints(bannerEl, textEl, dismissBtn) {
  if (!bannerEl || !textEl) {
    return { push() {} };
  }

  const state = {
    shown: parseInt(localStorage.getItem(STORAGE_KEY) || '0', 10),
  };

  dismissBtn?.addEventListener('click', () => hide());

  function hide() {
    bannerEl.setAttribute('hidden', 'hidden');
  }

  function show(message) {
    if (state.shown >= MAX_HINTS) return;
    textEl.textContent = message;
    bannerEl.removeAttribute('hidden');
    state.shown += 1;
    localStorage.setItem(STORAGE_KEY, String(state.shown));
  }

  return {
    push(message) {
      show(message);
    },
  };
}
