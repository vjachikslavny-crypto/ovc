function serializeForm(form) {
  const data = new FormData(form);
  return Object.fromEntries(data.entries());
}

function renderDrafts(drafts) {
  const container = document.getElementById('draft-list');
  container.innerHTML = '';

  drafts.forEach((draft, idx) => {
    const wrapper = document.createElement('label');
    wrapper.className = 'draft-item';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = true;
    checkbox.dataset.index = idx;
    wrapper.appendChild(checkbox);

    const body = document.createElement('div');
    body.className = 'draft-body';

    const title = document.createElement('div');
    title.className = 'draft-title';
    title.textContent = describeDraftTitle(draft);
    body.appendChild(title);

    const details = document.createElement('div');
    details.className = 'draft-details';
    details.textContent = describeDraftDetails(draft);
    body.appendChild(details);

    wrapper.appendChild(body);
    container.appendChild(wrapper);
  });
}

function describeDraftTitle(action) {
  switch (action.type) {
    case 'create_note':
      return `Создать заметку «${action.title}»`;
    case 'update_note':
      return `Обновить заметку ${action.id}`;
    case 'add_tag':
      return `Добавить тег «${action.tag}»`;
    case 'add_link':
      return `Добавить связь с «${action.to_title || 'выбранной заметкой'}»`;
    case 'add_source':
      return `Добавить источник ${new URL(action.source.url).hostname}`;
    default:
      return action.type;
  }
}

function describeDraftDetails(action) {
  switch (action.type) {
    case 'create_note':
      return snippet(action.content_md);
    case 'update_note':
      return snippet(action.patch_md || '');
    case 'add_tag':
      return `Вес: ${action.weight ?? 1}`;
    case 'add_link': {
      const confidence = Math.round((action.confidence ?? 0) * 100);
      return `Уверенность: ${confidence}%`;
    }
    case 'add_source':
      return safeHostname(action.source.url) ? `Источник: ${safeHostname(action.source.url)}` : action.source.title;
    default:
      return '';
  }
}

function snippet(text) {
  if (!text) return '';
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > 140 ? `${normalized.slice(0, 137)}…` : normalized;
}

function safeHostname(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return '';
  }
}

async function applyDraft(drafts, selectedIndexes) {
  const selected = drafts.filter((_, idx) => selectedIndexes.has(idx));
  const res = await fetch('/api/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft: selected })
  });
  if (!res.ok) {
    alert('Не удалось применить изменения');
    return;
  }
  const payload = await res.json();
  alert(`Применено действий: ${payload.applied}`);
}

function initChat() {
  const form = document.getElementById('chat-form');
  if (!form) return;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const values = serializeForm(form);
    const body = { text: values.message, noteId: values.noteId || null };
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!res.ok) {
      alert('Ошибка при обработке сообщения');
      return;
    }

    const payload = await res.json();
    document.getElementById('chat-response').classList.remove('hidden');
    document.getElementById('chat-reply').textContent = payload.reply;
    renderDrafts(payload.draft);

    const applyButton = document.getElementById('apply-draft');
    applyButton.classList.remove('hidden');
    applyButton.onclick = async () => {
      const checkboxes = document.querySelectorAll('#draft-list input[type="checkbox"]');
      const selected = new Set();
      checkboxes.forEach((checkbox) => {
        if (checkbox.checked) {
          selected.add(Number(checkbox.dataset.index));
        }
      });
      await applyDraft(payload.draft, selected);
    };
  });
}

document.addEventListener('DOMContentLoaded', initChat);
