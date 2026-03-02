function parseJsonError(response) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) return null;
  return response.json().catch(() => null);
}

document.addEventListener('DOMContentLoaded', () => {
  const authMode = window.__AUTH_MODE || document.body?.dataset?.authMode || 'local';
  const form = document.getElementById('register-form');
  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const email = String(formData.get('email') || '').trim();
    const password = String(formData.get('password') || '');
    const errorEl = document.getElementById('register-error');
    const successEl = document.getElementById('register-success');
    const registeredEmailEl = document.getElementById('registered-email');

    if (errorEl) errorEl.textContent = '';
    if (successEl) successEl.style.display = 'none';

    try {
      if (!email) {
        if (errorEl) errorEl.textContent = 'Введите email';
        return;
      }

      if (authMode === 'supabase') {
        if (!window.supabaseAuth) {
          if (errorEl) errorEl.textContent = 'Supabase не инициализирован';
          return;
        }
        await window.supabaseAuth.signUp(email, password);
        if (registeredEmailEl) registeredEmailEl.textContent = email;
        if (form) form.style.display = 'none';
        if (successEl) successEl.style.display = 'block';
        return;
      }

      // local / both / none: регистрация в локальной базе, username создается сервером из email
      const response = await fetch('/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const parsed = await parseJsonError(response);
        if (errorEl) errorEl.textContent = parsed?.detail || 'Ошибка регистрации';
        return;
      }

      window.location.href = '/login?registered=1';
    } catch (error) {
      if (errorEl) errorEl.textContent = error?.message || 'Ошибка регистрации';
    }
  });
});
