const STORAGE_KEY = 'ovc-theme';

document.addEventListener('DOMContentLoaded', () => {
  const root = document.body;
  const buttons = document.querySelectorAll('[data-theme]');

  const savedTheme = localStorage.getItem(STORAGE_KEY) || root.dataset.theme || 'clean';
  applyTheme(savedTheme);

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const theme = btn.getAttribute('data-theme') || 'clean';
      applyTheme(theme);
    });
  });

  function applyTheme(theme) {
    root.dataset.theme = theme;
    root.classList.remove('theme-clean', 'theme-brief');
    root.classList.add(theme === 'brief' ? 'theme-brief' : 'theme-clean');
    localStorage.setItem(STORAGE_KEY, theme);
    document.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }));
  }
});
