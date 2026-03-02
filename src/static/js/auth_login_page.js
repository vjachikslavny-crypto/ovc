function parseJsonError(response) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) return null;
  return response.json().catch(() => null);
}

async function submitLocalLogin(identifier, password) {
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  });

  if (response.ok) {
    let token = null;
    if (typeof window.refreshAccessToken === 'function') {
      token = await window.refreshAccessToken();
    }
    if (!token) {
      const hasRefreshCookie = document.cookie.includes('refresh_token=');
      return {
        ok: false,
        status: 401,
        error: hasRefreshCookie
          ? 'Сессия не активировалась. Обновите страницу и попробуйте снова.'
          : 'Сессия не установлена (проверьте настройки cookie).',
      };
    }
    return { ok: true };
  }

  const parsed = await parseJsonError(response);
  return {
    ok: false,
    status: response.status,
    error: parsed?.detail || 'Ошибка входа',
  };
}

document.addEventListener('DOMContentLoaded', () => {
  const authMode = window.__AUTH_MODE || document.body?.dataset?.authMode || 'local';

  const loginForm = document.getElementById('login-form');
  loginForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(loginForm);
    const identifier = String(formData.get('identifier') || '').trim();
    const password = String(formData.get('password') || '');

    const errorEl = document.getElementById('login-error');
    if (errorEl) errorEl.textContent = '';

    try {
      if (!identifier) {
        if (errorEl) errorEl.textContent = 'Введите логин или email';
        return;
      }

      if (authMode === 'local' || authMode === 'none') {
        const localResult = await submitLocalLogin(identifier, password);
        if (!localResult.ok) {
          if (errorEl) errorEl.textContent = localResult.error;
          return;
        }
        window.location.href = '/';
        return;
      }

      if (authMode === 'supabase') {
        if (!window.supabaseAuth) {
          if (errorEl) errorEl.textContent = 'Supabase не инициализирован';
          return;
        }
        if (!identifier.includes('@')) {
          if (errorEl) errorEl.textContent = 'Для входа через Supabase нужен email';
          return;
        }
        await window.supabaseAuth.signIn(identifier, password);
        window.location.href = '/';
        return;
      }

      // authMode === "both": сначала local, затем fallback в Supabase (только для email)
      const localResult = await submitLocalLogin(identifier, password);
      if (localResult.ok) {
        window.location.href = '/';
        return;
      }

      if (!identifier.includes('@') || !window.supabaseAuth) {
        if (errorEl) errorEl.textContent = localResult.error;
        return;
      }

      await window.supabaseAuth.signIn(identifier, password);
      window.location.href = '/';
    } catch (error) {
      if (errorEl) errorEl.textContent = error?.message || 'Ошибка сети';
    }
  });
});
