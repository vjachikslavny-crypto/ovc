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
    bubbleEl.style.left = `${rect.left + rect.width / 2}px`;
    bubbleEl.style.top = `${rect.top + window.scrollY - 12}px`;
    bubbleEl.setAttribute('aria-hidden', 'false');
  });

  bubbleEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    event.preventDefault();
    applyCommand(button.dataset.action);
    hideBubble();
  });

  document.addEventListener('mousedown', (event) => {
    if (!bubbleEl.contains(event.target)) {
      hideBubble();
    }
  });

  function hideBubble() {
    bubbleEl.setAttribute('aria-hidden', 'true');
  }
}
