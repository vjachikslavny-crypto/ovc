document.addEventListener('DOMContentLoaded', () => {
  const toggles = document.querySelectorAll('[data-password-toggle]');
  toggles.forEach((button) => {
    button.addEventListener('click', () => {
      const wrapper = button.closest('.password-field');
      const input = wrapper?.querySelector('input[type="password"], input[type="text"]');
      if (!input) return;

      const isHidden = input.type === 'password';
      input.type = isHidden ? 'text' : 'password';
      button.setAttribute('aria-label', isHidden ? 'Скрыть пароль' : 'Показать пароль');
      button.setAttribute('title', isHidden ? 'Скрыть пароль' : 'Показать пароль');
      button.textContent = isHidden ? '🙈' : '👁';
    });
  });
});
