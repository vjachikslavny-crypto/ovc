const COMMANDS = {
  bold: 'bold',
  italic: 'italic',
  link: 'createLink',
  list: 'insertUnorderedList',
  quote: 'formatBlock',
  align: 'justifyFull',
};

export function initToolbar(toolbarEl) {
  if (!toolbarEl) return;
  toolbarEl.addEventListener('click', (event) => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    event.preventDefault();
    const action = button.dataset.action;
    applyCommand(action);
  });
}

export function applyCommand(action) {
  if (!action) return;
  const command = COMMANDS[action];
  if (!command) return;

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
