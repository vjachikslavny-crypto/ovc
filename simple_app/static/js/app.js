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

    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(draft, null, 2);
    wrapper.appendChild(pre);
    container.appendChild(wrapper);
  });
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
