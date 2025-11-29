const STORAGE_KEY = 'ovc-theme';

document.addEventListener('DOMContentLoaded', () => {
  const root = document.body;
  const buttons = document.querySelectorAll('[data-theme]');
  let currentTheme = localStorage.getItem(STORAGE_KEY) || root.dataset.theme || 'clean';

  // Применяем тему без диспатча события при загрузке
  applyThemeStyles(currentTheme);

  buttons.forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation(); // Предотвращаем всплытие
      const theme = btn.getAttribute('data-theme') || 'clean';
      if (theme !== currentTheme) {
        currentTheme = theme;
        applyThemeStyles(theme);
        document.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }));
      }
    });
  });

  function applyThemeStyles(theme) {
    root.dataset.theme = theme;
    root.classList.remove('theme-clean', 'theme-brief');
    root.classList.add(theme === 'brief' ? 'theme-brief' : 'theme-clean');
    localStorage.setItem(STORAGE_KEY, theme);
  }
});
