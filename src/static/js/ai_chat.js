const ESC_KEY = 'Escape';

/**
 * AI Chat panel — sends messages to /api/chat and displays responses.
 *
 * Modes:
 *   chat      — free-form conversation about the note
 *   summarize — concise summary of note content
 *   detailed  — AI-enriched detailed summary
 *   explain   — explain note content
 *
 * Draft actions from summarize/detailed are shown as a preview
 * with Approve / Reject buttons instead of being auto-committed.
 */
export function initAiChat({ rootEl, toggleBtn, getNoteId, onBlocksCommitted }) {
  if (!rootEl) return { update() {} };

  const messagesEl = rootEl.querySelector('.ai-chat__messages');
  const inputEl = rootEl.querySelector('.ai-chat__input');
  const sendBtn = rootEl.querySelector('.ai-chat__send');
  const modeSelect = rootEl.querySelector('.ai-chat__mode');
  const closeBtn = rootEl.querySelector('[data-close-chat]');

  // Each message: { role, text, mode, draft?, draftStatus? }
  // draftStatus: null | 'pending' | 'applied' | 'rejected'
  const state = { messages: [], loading: false };

  // Toggle panel
  toggleBtn?.addEventListener('click', () => {
    const next = !rootEl.classList.contains('ai-chat--open');
    setOpen(next);
    if (next) inputEl?.focus();
  });

  closeBtn?.addEventListener('click', () => setOpen(false));

  document.addEventListener('keydown', (e) => {
    if (e.key === ESC_KEY && rootEl.classList.contains('ai-chat--open')) {
      setOpen(false);
    }
  });

  // Send on Enter (Shift+Enter = newline)
  inputEl?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  sendBtn?.addEventListener('click', () => send());

  // Update placeholder based on mode
  modeSelect?.addEventListener('change', () => {
    updatePlaceholder();
  });

  // Outside click closes on mobile
  document.addEventListener('click', (e) => {
    if (!isMobile()) return;
    if (!rootEl.classList.contains('ai-chat--open')) return;
    if (rootEl.contains(e.target)) return;
    if (toggleBtn?.contains(e.target)) return;
    setOpen(false);
  });

  function setOpen(flag) {
    rootEl.classList.toggle('ai-chat--open', flag);
    rootEl.setAttribute('aria-hidden', flag ? 'false' : 'true');
  }

  function isMobile() {
    return window.matchMedia('(max-width: 899px)').matches;
  }

  function updatePlaceholder() {
    if (!inputEl) return;
    const mode = modeSelect?.value || 'chat';
    const placeholders = {
      chat: 'Задайте вопрос про заметку...',
      summarize_text: 'Нажмите отправить для краткого конспекта (или добавьте текст)',
      detailed: 'Нажмите отправить для полного конспекта (или добавьте текст)',
      explain: 'Что объяснить? (нажмите отправить для всей заметки)',
    };
    inputEl.placeholder = placeholders[mode] || placeholders.chat;
  }

  updatePlaceholder();

  async function send() {
    const text = inputEl?.value?.trim() || '';
    const mode = modeSelect?.value || 'chat';

    // В режиме chat текст обязателен
    if (mode === 'chat' && !text) return;
    if (state.loading) return;

    const noteId = typeof getNoteId === 'function' ? getNoteId() : null;

    // Add user message
    const displayText = text || modeLabels(mode);
    addMessage('user', displayText, mode);
    if (inputEl) inputEl.value = '';

    state.loading = true;
    updateSendButton();

    try {
      const body = { text, mode };
      if (noteId) body.noteId = noteId;

      // Build history: last 10 messages across all modes (excluding current)
      const allConversation = state.messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .slice(0, -1) // exclude current user message (just added)
        .slice(-10);   // last 10 messages for context
      if (allConversation.length > 0) {
        body.messages = allConversation.map((m) => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          text: m.mode !== mode ? `[${modeLabels(m.mode)}] ${m.text}` : m.text,
        }));
      }

      // Используем SSE-стриминг для всех режимов
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errText = await res.text().catch(() => res.statusText);
        throw new Error(errText || `HTTP ${res.status}`);
      }

      // Стриминг: создаём пустое сообщение и обновляем его по мере поступления
      const msgIndex = state.messages.length;
      addMessage('assistant', '', mode);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let streamedText = '';
      let pendingDraft = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          let event;
          try { event = JSON.parse(jsonStr); } catch { continue; }

          if (event.type === 'delta') {
            streamedText += event.text;
            state.messages[msgIndex].text = streamedText;
            renderMessages();
          } else if (event.type === 'reply') {
            streamedText = event.text;
            state.messages[msgIndex].text = streamedText;
            renderMessages();
          } else if (event.type === 'draft') {
            pendingDraft = event.draft;
          } else if (event.type === 'error') {
            state.messages[msgIndex].text = event.message || 'Ошибка AI';
            state.messages[msgIndex].role = 'error';
            renderMessages();
          }
        }
      }

      // Применяем draft если пришёл
      if (pendingDraft && pendingDraft.length > 0) {
        state.messages[msgIndex].draft = pendingDraft;
        state.messages[msgIndex].draftStatus = 'pending';
        renderMessages();
      }

      // Если текст пуст после стрима
      if (!state.messages[msgIndex].text && state.messages[msgIndex].role !== 'error') {
        state.messages[msgIndex].text = 'Нет ответа';
        renderMessages();
      }

    } catch (err) {
      addMessage('error', `Ошибка: ${err.message}`);
    } finally {
      state.loading = false;
      updateSendButton();
    }
  }

  function modeLabels(mode) {
    const labels = {
      chat: 'Чат',
      explain: 'Объяснение',
      summarize_text: 'Краткий конспект',
      detailed: 'Полный конспект',
    };
    return labels[mode] || mode;
  }

  function addMessage(role, text, modeParam = null, draft = null) {
    const currentMode = modeParam || modeSelect?.value || 'chat';
    const msg = { role, text, mode: currentMode };
    if (draft) {
      msg.draft = draft;
      msg.draftStatus = 'pending';
    }
    state.messages.push(msg);
    renderMessages();
  }

  /** Извлекает читаемый текст из массива draft actions для превью */
  function extractDraftPreviewText(draft) {
    const lines = [];
    for (const action of draft) {
      if (action.type !== 'insert_block') continue;
      const block = action.block;
      if (!block) continue;
      const data = block.data || {};

      if (block.type === 'heading') {
        const level = data.level || 2;
        const prefix = '#'.repeat(Math.min(level, 4));
        lines.push(`${prefix} ${data.text || ''}`);
      } else if (block.type === 'paragraph') {
        const parts = data.parts || [];
        const text = parts.map((p) => p.text || '').join('');
        if (text.trim()) lines.push(text);
      } else if (block.type === 'bulletList' || block.type === 'numberList') {
        const items = data.items || [];
        items.forEach((item) => {
          const t = typeof item === 'string' ? item : (item.text || '');
          lines.push(`• ${t}`);
        });
      } else if (block.type === 'quote') {
        lines.push(`> ${data.text || ''}`);
      } else if (data.text) {
        lines.push(data.text);
      }
    }
    return lines.join('\n');
  }

  function renderMessages() {
    if (!messagesEl) return;
    messagesEl.innerHTML = '';

    state.messages.forEach((m, idx) => {
      const msgDiv = document.createElement('div');
      msgDiv.className = `ai-chat__msg ai-chat__msg--${m.role}`;

      // Метка отправителя
      const label =
        m.role === 'user' ? 'Вы' :
        m.role === 'assistant' ? 'AI' : '';

      if (label) {
        const labelEl = document.createElement('span');
        labelEl.className = 'ai-chat__msg-label';
        labelEl.textContent = label;
        msgDiv.appendChild(labelEl);
      }

      // Текст сообщения
      const textEl = document.createElement('span');
      textEl.className = 'ai-chat__msg-text';
      if (m.role === 'assistant') {
        textEl.innerHTML = formatMarkdown(m.text);
      } else {
        textEl.textContent = m.text;
      }
      msgDiv.appendChild(textEl);

      // Если есть draft — рисуем карточку превью
      if (m.draft && m.draft.length > 0) {
        const previewCard = document.createElement('div');
        previewCard.className = 'ai-draft-preview';

        if (m.draftStatus === 'applied') {
          previewCard.classList.add('ai-draft-preview--applied');
          previewCard.innerHTML = `
            <div class="ai-draft-preview__header">✅ Применено к заметке</div>
            <div class="ai-draft-preview__body">${formatMarkdown(extractDraftPreviewText(m.draft))}</div>
          `;
        } else if (m.draftStatus === 'rejected') {
          previewCard.classList.add('ai-draft-preview--rejected');
          previewCard.innerHTML = `
            <div class="ai-draft-preview__header">❌ Отклонено</div>
          `;
        } else {
          // pending — показываем превью + кнопки
          const previewText = extractDraftPreviewText(m.draft);
          previewCard.innerHTML = `
            <div class="ai-draft-preview__header">📝 Предложенные изменения</div>
            <div class="ai-draft-preview__body">${formatMarkdown(previewText)}</div>
          `;

          const actions = document.createElement('div');
          actions.className = 'ai-draft-preview__actions';

          const applyBtn = document.createElement('button');
          applyBtn.className = 'ai-draft-btn ai-draft-btn--apply';
          applyBtn.textContent = '✅ Применить к заметке';
          applyBtn.addEventListener('click', () => commitDraft(idx));

          const rejectBtn = document.createElement('button');
          rejectBtn.className = 'ai-draft-btn ai-draft-btn--reject';
          rejectBtn.textContent = '❌ Отклонить';
          rejectBtn.addEventListener('click', () => rejectDraft(idx));

          actions.appendChild(applyBtn);
          actions.appendChild(rejectBtn);
          previewCard.appendChild(actions);
        }

        msgDiv.appendChild(previewCard);
      }

      messagesEl.appendChild(msgDiv);
    });

    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function commitDraft(msgIndex) {
    const msg = state.messages[msgIndex];
    if (!msg || !msg.draft || msg.draftStatus !== 'pending') return;

    try {
      // Помечаем каждый блок как созданный ИИ
      const taggedDraft = msg.draft.map((action) => {
        if (action.type === 'insert_block' && action.block && action.block.data) {
          return {
            ...action,
            block: {
              ...action.block,
              data: { ...action.block.data, source: 'ai' },
            },
          };
        }
        return action;
      });

      const commitRes = await fetch('/api/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ draft: taggedDraft }),
      });

      if (commitRes.ok) {
        msg.draftStatus = 'applied';
        renderMessages();
        // Обновляем холст заметки без перезагрузки
        if (typeof onBlocksCommitted === 'function') {
          onBlocksCommitted();
        }
      } else {
        const errText = await commitRes.text().catch(() => '');
        addMessage('error', `Ошибка коммита: ${errText || commitRes.status}`);
      }
    } catch (e) {
      console.error('AI Draft commit failed', e);
      addMessage('error', `Ошибка: ${e.message}`);
    }
  }

  function rejectDraft(msgIndex) {
    const msg = state.messages[msgIndex];
    if (!msg || msg.draftStatus !== 'pending') return;
    msg.draftStatus = 'rejected';
    renderMessages();
  }

  function updateSendButton() {
    if (sendBtn) {
      sendBtn.disabled = state.loading;
      sendBtn.textContent = state.loading ? '...' : '→';
    }
  }

  /** Simple markdown → HTML (headers, bold, italic, lists, code). */
  function formatMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Headers
    html = html.replace(/^### (.+)$/gm, '<strong>$1</strong>');
    html = html.replace(/^## (.+)$/gm, '<strong style="font-size:1.1em">$1</strong>');
    html = html.replace(/^# (.+)$/gm, '<strong style="font-size:1.2em">$1</strong>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // List items
    html = html.replace(/^- (.+)$/gm, '&bull; $1');
    html = html.replace(/^\d+\. (.+)$/gm, '&bull; $1');
    // Line breaks
    html = html.replace(/\n/g, '<br>');

    return html;
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
    update() {},
    open() { setOpen(true); },
    close() { setOpen(false); },
  };
}
