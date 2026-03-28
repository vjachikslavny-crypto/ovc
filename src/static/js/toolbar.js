const COMMANDS = {
  bold: 'bold',
  italic: 'italic',
  link: 'createLink',
  list: 'insertUnorderedList',
  quote: 'formatBlock',
  align: 'justifyFull',
};

let trackedRoot = null;
let savedRange = null;
let selectionListenerAttached = false;
let selectionTimer = null;
const SELECTION_DEBOUNCE = 40;

function handleSelectionChange() {
  if (selectionTimer) {
    clearTimeout(selectionTimer);
  }
  selectionTimer = setTimeout(() => {
    captureSelection();
    selectionTimer = null;
  }, SELECTION_DEBOUNCE);
}

function captureSelection() {
  if (!trackedRoot) return;
  const selection = document.getSelection();
  if (!selection || selection.rangeCount === 0) return;
  const range = selection.getRangeAt(0);
  const container = getRangeElement(range);
  if (!container || !trackedRoot.contains(container)) return;
  const previous = savedRange;
  if (range.collapsed && previous && !previous.collapsed) {
    return;
  }
  savedRange = range.cloneRange();
}

function restoreSelection() {
  if (!savedRange) return;
  const selection = document.getSelection();
  if (!selection) return;
  try {
    selection.removeAllRanges();
    const clone = savedRange.cloneRange();
    selection.addRange(clone);
    focusRange(clone);
  } catch (error) {
    savedRange = null;
  }
}

export function initToolbar(toolbarEl, rootEl) {
  trackedRoot = rootEl || trackedRoot;

  if (!selectionListenerAttached) {
    document.addEventListener('selectionchange', handleSelectionChange);
    selectionListenerAttached = true;
  }

  if (!toolbarEl) return;

  toolbarEl.addEventListener('mousedown', (event) => {
    if (event.target.closest('[data-action]')) {
      captureSelection();
      const coarsePointer = window.matchMedia?.('(pointer: coarse)')?.matches;
      if (!coarsePointer) {
        event.preventDefault();
        restoreSelection();
      }
    }
  });

  toolbarEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    event.preventDefault();
    applyCommand(button.dataset.action);
  });
}

export function applyCommand(action) {
  if (!action) return;
  const command = COMMANDS[action];
  if (!command) return;

  restoreSelection();

  if (action === 'quote') {
    document.execCommand(command, false, 'blockquote');
    return;
  }

  if (action === 'link') {
    const url = prompt('Вставьте ссылку');
    if (url) {
      document.execCommand(command, false, url);
    }
    return;
  }

  document.execCommand(command, false, null);
}

function focusRange(range) {
  if (!range) return;
  const node = getRangeElement(range);
  if (node && typeof node.focus === 'function') {
    node.focus({ preventScroll: true });
  }
}

function getRangeElement(range) {
  if (!range) return null;
  let container = range.commonAncestorContainer;
  if (!container) return null;
  if (container.nodeType === Node.TEXT_NODE) {
    container = container.parentElement;
  }
  return container;
}

export function clearSelectionSnapshot() {
  savedRange = null;
}

export function rememberSelection() {
  captureSelection();
}
