(function bootstrapAppConfig() {
  const body = document.body;
  if (!body) return;

  const read = (key, fallback = '') => {
    const value = body.dataset[key];
    return value == null ? fallback : value;
  };

  window.__AUTH_MODE = read('authMode', 'local');
  window.__DESKTOP_MODE = read('desktopMode', 'false') === 'true';
  window.__SUPABASE_URL = read('supabaseUrl', '');
  window.__SUPABASE_ANON_KEY = read('supabaseAnonKey', '');
})();
