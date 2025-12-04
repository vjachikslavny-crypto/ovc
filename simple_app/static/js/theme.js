const STORAGE_KEY = 'ovc-theme';

document.addEventListener('DOMContentLoaded', () => {
  const htmlRoot = document.documentElement; // <html> элемент для :root в CSS
  const bodyRoot = document.body;
  const buttons = document.querySelectorAll('[data-theme]');
  const select = document.getElementById('theme-switcher');
  let currentTheme = localStorage.getItem(STORAGE_KEY) || htmlRoot.dataset.theme || bodyRoot.dataset.theme || 'default';

  // Применяем тему без диспатча события при загрузке
  applyThemeStyles(currentTheme);
  if (select) {
    // Устанавливаем значение select, если тема найдена в опциях
    const optionValues = Array.from(select.options).map(opt => opt.value);
    if (optionValues.includes(currentTheme)) {
      select.value = currentTheme;
    } else if (currentTheme === 'brief' || currentTheme === 'clean') {
      // Если тема brief или clean, устанавливаем default (так как они используют те же стили)
      select.value = 'default';
    }
  }

  buttons.forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation(); // Предотвращаем всплытие
      const theme = btn.getAttribute('data-theme') || 'default';
      if (theme !== currentTheme) {
        currentTheme = theme;
        applyThemeStyles(theme);
        document.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }));
      }
    });
  });

  select?.addEventListener('change', () => {
    const theme = select.value || 'default';
    if (theme !== currentTheme) {
      currentTheme = theme;
      applyThemeStyles(theme);
      document.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }));
    }
  });

  function applyThemeStyles(theme) {
    // Устанавливаем data-theme на <html> элемент, так как CSS использует :root
    htmlRoot.dataset.theme = theme || 'default';
    // Также обновляем body для совместимости
    bodyRoot.dataset.theme = theme || 'default';
    bodyRoot.classList.remove('theme-clean', 'theme-brief');
    if (theme === 'brief' || theme === 'clean' || theme === 'default') {
      bodyRoot.classList.add('theme-brief');
    } else {
      bodyRoot.classList.add('theme-clean');
    }
    localStorage.setItem(STORAGE_KEY, theme);
  }
});
