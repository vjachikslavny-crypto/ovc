function parseJsonError(response) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) return null;
  return response.json().catch(() => null);
}

document.addEventListener('DOMContentLoaded', () => {
  const authMode = window.__AUTH_MODE || document.body?.dataset?.authMode || 'local';
  const canUseSupabase = authMode === 'supabase' || authMode === 'both';
  const form = document.getElementById('register-form');
  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const email = String(formData.get('email') || '').trim();
    const password = String(formData.get('password') || '');
    const errorEl = document.getElementById('register-error');
    const successEl = document.getElementById('register-success');
    const registeredEmailEl = document.getElementById('registered-email');
    const successTextEl = document.getElementById('register-success-text');

    const showSuccess = (emailValue, viaEmailConfirmation) => {
      if (registeredEmailEl) registeredEmailEl.textContent = emailValue;
      if (successTextEl) {
        if (viaEmailConfirmation) {
          successTextEl.innerHTML = 'Письмо для подтверждения отправлено на <strong id="registered-email"></strong>.';
          const inlineEmail = successTextEl.querySelector('#registered-email');
          if (inlineEmail) inlineEmail.textContent = emailValue;
        } else {
          successTextEl.textContent = `Аккаунт создан для ${emailValue}. Теперь можно войти.`;
        }
      }
      if (form) form.style.display = 'none';
      if (successEl) successEl.style.display = 'block';
    };

    if (errorEl) errorEl.textContent = '';
    if (successEl) successEl.style.display = 'none';

    try {
      if (!email) {
        if (errorEl) errorEl.textContent = 'Введите email';
        return;
      }

      if (canUseSupabase && window.supabaseAuth) {
        if (!window.supabaseAuth) {
          if (errorEl) errorEl.textContent = 'Supabase не инициализирован';
          return;
        }
        try {
          await window.supabaseAuth.signUp(email, password);
          showSuccess(email, true);
          return;
        } catch (sbError) {
          // In mixed mode keep registration available even if Supabase is temporarily unavailable.
          if (authMode === 'supabase') {
            throw sbError;
          }
        }
      }

      // local / none / both fallback: registration in local DB.
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

      // Local registration now also sends confirmation email.
      showSuccess(email, true);
    } catch (error) {
      if (errorEl) errorEl.textContent = error?.message || 'Ошибка регистрации';
    }
  });
});
