function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('change-password-form');
  if (!form) return;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const csrf = getCookie('csrf_token');
    const errorEl = document.getElementById('change-password-error');
    if (errorEl) errorEl.textContent = '';

    if (!csrf) {
      if (errorEl) errorEl.textContent = 'CSRF токен не найден';
      return;
    }

    try {
      const response = await fetch('/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
        },
        body: JSON.stringify({
          old_password: formData.get('old_password'),
          new_password: formData.get('new_password'),
        }),
      });

      if (response.ok) {
        window.alert('Пароль изменен. Войдите заново.');
        window.location.href = '/login';
        return;
      }

      const data = await response.json().catch(() => ({}));
      if (errorEl) errorEl.textContent = data.detail || 'Ошибка смены пароля';
    } catch (_) {
      if (errorEl) errorEl.textContent = 'Ошибка сети';
    }
  });
});
