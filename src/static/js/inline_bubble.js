import { applyCommand } from './toolbar.js';

export function initInlineBubble(bubbleEl, canvas) {
  if (!bubbleEl || !canvas) return;

  document.addEventListener('selectionchange', () => {
    const selection = document.getSelection();
    if (!selection || selection.isCollapsed) {
      hideBubble();
      return;
    }
    const range = selection.getRangeAt(0);
    if (!canvas.contains(range.commonAncestorContainer)) {
      hideBubble();
      return;
    }
    const rect = range.getBoundingClientRect();
    if (!rect) {
      hideBubble();
      return;
    }

    bubbleEl.style.position = 'fixed';
    bubbleEl.setAttribute('aria-hidden', 'false');

    const viewportWidth = window.visualViewport?.width || window.innerWidth;
    const viewportHeight = window.visualViewport?.height || window.innerHeight;
    const bubbleWidth = bubbleEl.offsetWidth || 300;
    const bubbleHeight = bubbleEl.offsetHeight || 48;

    let centerX = rect.left + rect.width / 2;
    const minCenter = 12 + bubbleWidth / 2;
    const maxCenter = viewportWidth - 12 - bubbleWidth / 2;
    centerX = Math.max(minCenter, Math.min(maxCenter, centerX));

    let top = rect.top - 12;
    let placement = 'top';
    if (top - bubbleHeight < 8) {
      top = rect.bottom + 12 + bubbleHeight;
      placement = 'bottom';
    }
    if (top > viewportHeight - 8) {
      top = viewportHeight - 8;
      placement = 'top';
    }

    bubbleEl.style.left = `${centerX}px`;
    bubbleEl.style.top = `${top}px`;
    bubbleEl.dataset.placement = placement;
    bubbleEl.setAttribute('aria-hidden', 'false');
  });

  bubbleEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    event.preventDefault();
    applyCommand(button.dataset.action);
    hideBubble();
  });

  const onOutside = (event) => {
    if (!bubbleEl.contains(event.target)) {
      hideBubble();
    }
  };
  document.addEventListener('mousedown', onOutside);
  document.addEventListener('touchstart', onOutside, { passive: true });

  function hideBubble() {
    bubbleEl.setAttribute('aria-hidden', 'true');
  }
}
