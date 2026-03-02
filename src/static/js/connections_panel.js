const ESC_KEY = 'Escape';

export function initConnectionsPanel({
  rootEl,
  toggleBtn,
  getNoteId,
  onOpenNote,
  fetchOptions,
  addLink,
}) {
  if (!rootEl) {
    return { update() {} };
  }

  const bodyEl = rootEl.querySelector('#connections-body') || rootEl;
  const countEl = rootEl.querySelector('#connections-count');
  const state = {
    linksFrom: [],
    linksTo: [],
    options: [],
    optionsLoaded: false,
    addExpanded: false,
    loadingOptions: false,
  };

  render();

  toggleBtn?.addEventListener('click', () => {
    const next = !rootEl.classList.contains('connections-panel--open');
    setOpen(next);
    if (next) {
      ensureOptions();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === ESC_KEY && rootEl.classList.contains('connections-panel--open')) {
      setOpen(false);
    }
  });

  rootEl.addEventListener('click', (event) => {
    const linkItem = event.target.closest('.conn-item');
    if (linkItem?.dataset.linkId) {
      onOpenNote?.(linkItem.dataset.linkId);
      setOpen(false);
      return;
    }
    const toggleAdd = event.target.closest('[data-action="toggle-add"]');
    if (toggleAdd) {
      event.preventDefault();
      event.stopPropagation();
      state.addExpanded = !state.addExpanded;
      if (state.addExpanded) ensureOptions();
      render();
      return;
    }
  });

  rootEl.addEventListener('submit', async (event) => {
    const form = event.target.closest('.conn-add__form');
    if (!form) return;
    event.preventDefault();
    const statusEl = form.querySelector('[data-role="conn-status"]');
    const selectEl = form.querySelector('select[name="toId"]');
    const reasonEl = form.querySelector('input[name="reason"]');
    if (!selectEl) return;
    const toId = selectEl.value.trim();
    const reason = reasonEl?.value || '';
    statusEl.textContent = '';
    disableForm(form, true);
    try {
      await addLink({ toId, reason });
      form.reset();
      state.addExpanded = false;
      render();
    } catch (error) {
      statusEl.textContent = error?.message || 'Не удалось добавить связь';
    } finally {
      disableForm(form, false);
    }
  });

  function disableForm(form, disabled) {
    form.querySelectorAll('select, input, button').forEach((el) => {
      el.disabled = disabled;
    });
  }

  function setOpen(flag) {
    rootEl.classList.toggle('connections-panel--open', flag);
  }

  async function ensureOptions() {
    if (state.optionsLoaded || state.loadingOptions || !fetchOptions) return;
    try {
      state.loadingOptions = true;
      const result = await fetchOptions();
      if (Array.isArray(result)) {
        state.options = result;
        state.optionsLoaded = true;
        render();
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.warn('Failed to load linkable notes', error);
    } finally {
      state.loadingOptions = false;
    }
  }

  function render() {
    // Объединяем все связи в один список
    const allLinks = [
      ...(Array.isArray(state.linksFrom) ? state.linksFrom : []),
      ...(Array.isArray(state.linksTo) ? state.linksTo : []),
    ];
    const total = allLinks.length;
    if (countEl) {
      countEl.textContent = String(total);
    }
    bodyEl.innerHTML = `
      ${renderGroup('Связи', allLinks, 'all')}
      ${renderAddSection()}
    `;
  }

  function renderGroup(title, list = [], type) {
    const safeList = Array.isArray(list) ? list : [];
    if (!safeList.length) {
      return `
        <section class="conn-group conn-group--${type}">
          <header class="conn-group__header">
            <span>${title}</span>
            <span class="conn-group__badge">0</span>
          </header>
          <p class="conn-group__empty">Связей нет</p>
        </section>
      `;
    }
    const items = safeList
      .map((link) => {
        const titleText = escapeHtml(link.title || 'Без названия');
        const reason = link.reason && link.reason !== 'manual'
          ? `<span class="conn-item__reason">${escapeHtml(link.reason)}</span>`
          : '';
        const directionId = link.toId || link.fromId || link.id;
        return `
          <button type="button" class="conn-item" data-link-id="${directionId}">
            <span class="conn-item__title">${titleText}</span>
            ${reason}
          </button>
        `;
      })
      .join('');
    return `
      <section class="conn-group conn-group--${type}">
        <header class="conn-group__header">
          <span>${title}</span>
          <span class="conn-group__badge">${safeList.length}</span>
        </header>
        <div class="conn-group__items">
          ${items}
        </div>
      </section>
    `;
  }

  function renderAddSection() {
    const currentNoteId = typeof getNoteId === 'function' ? getNoteId() : null;
    const expandedAttr = state.addExpanded ? 'data-expanded="true"' : 'data-expanded="false"';
    const availableOptions = state.options.filter((item) => item.id && item.id !== currentNoteId);
    const selectDisabledAttr = availableOptions.length ? '' : 'disabled';
    const optionsHtml = availableOptions
      .map((item) => `<option value="${item.id}">${escapeHtml(item.title || 'Без названия')}</option>`)
      .join('');
    const formHiddenClass = state.addExpanded ? '' : 'conn-add__form--hidden';
    return `
      <section class="conn-add" ${expandedAttr}>
        <button type="button" class="conn-add__toggle" data-action="toggle-add">+ Связь</button>
        <form class="conn-add__form ${formHiddenClass}">
          <select name="toId" required ${selectDisabledAttr}>
            <option value="">Выберите заметку</option>
            ${optionsHtml}
          </select>
          <input type="text" name="reason" placeholder="Описание (опционально)" />
          <div class="conn-add__actions">
            <button type="submit" class="pill-button pill-button--compact">Добавить</button>
            <span class="conn-add__status" data-role="conn-status"></span>
          </div>
          <p class="conn-add__hint" ${availableOptions.length ? 'hidden' : ''}>Нет доступных заметок для связи</p>
        </form>
      </section>
    `;
  }

  function escapeHtml(value = '') {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  return {
    update(noteState) {
      if (!noteState) return;
      state.linksFrom = noteState.linksFrom || [];
      state.linksTo = noteState.linksTo || [];
      render();
    },
  };
}
