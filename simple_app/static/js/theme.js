const STORAGE_KEY = 'ovc:theme';

document.addEventListener('DOMContentLoaded', () => {
  const saved = localStorage.getItem(STORAGE_KEY);
  const fallback = document.body.dataset.theme || 'brief';
  const theme = saved || fallback;
  applyTheme(theme);

  function applyTheme(value) {
    if (value) {
      document.documentElement.setAttribute('data-theme', value);
      document.body.dataset.theme = value;
    } else {
      document.documentElement.removeAttribute('data-theme');
      document.body.dataset.theme = 'brief';
    }
  }
});
