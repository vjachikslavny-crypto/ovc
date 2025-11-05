export function initInspector(panelEl) {
  if (!panelEl) {
    return { update() {} };
  }

  const tagsEl = panelEl.querySelector('#inspector-tags');
  const linksEl = panelEl.querySelector('#inspector-links');
  const propsEl = panelEl.querySelector('#inspector-properties');
  panelEl.querySelector('[data-close-inspector]')?.addEventListener('click', () => {
    panelEl.setAttribute('aria-hidden', 'true');
  });

  return {
    update(note) {
      renderTags(tagsEl, note?.tags || []);
      renderLinks(linksEl, note?.linksFrom || [], note?.linksTo || []);
      renderProperties(propsEl, note?.passport || {});
    },
  };
}

function renderTags(container, tags) {
  if (!container) return;
  container.innerHTML = '';
  tags.forEach((tag) => {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.textContent = tag;
    container.appendChild(chip);
  });
}

function renderLinks(container, fromLinks, toLinks) {
  if (!container) return;
  container.innerHTML = '';
  [...fromLinks, ...toLinks].forEach((link) => {
    const li = document.createElement('li');
    const anchor = document.createElement('a');
    anchor.href = `/notes/${link.toId || link.fromId}`;
    anchor.textContent = link.title || link.toId || link.fromId;
    li.append(anchor);
    container.appendChild(li);
  });
}

function renderProperties(container, passport) {
  if (!container) return;
  container.innerHTML = '';
  Object.entries(passport || {}).forEach(([key, value]) => {
    const dt = document.createElement('dt');
    dt.textContent = key;
    const dd = document.createElement('dd');
    dd.textContent = formatValue(value);
    container.append(dt, dd);
  });
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  if (value && typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value ?? '');
}
