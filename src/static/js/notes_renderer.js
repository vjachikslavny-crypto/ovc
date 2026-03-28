export function renderNoteCard(note, options = {}) {
  const { onDeleted } = options;
  const article = document.createElement('article');
  article.className = 'note-card';
  article.dataset.noteId = note.id;

  // Клик по карточке открывает заметку
  article.addEventListener('click', (e) => {
    // Не переходим, если кликнули на редактируемый заголовок или кнопку
    if (e.target.closest('.note-card__title') && document.activeElement === e.target.closest('.note-card__title')) return;
    if (e.target.closest('.pill-button')) return;
    window.location.href = `/notes/${note.id}`;
  });

  const title = document.createElement('h2');
  title.contentEditable = true;
  title.spellcheck = false;
  title.textContent = note.title || 'Без названия';
  title.className = 'note-card__title';
  
  let saveTimeout = null;
  let originalTitle = note.title || 'Без названия';
  
  title.addEventListener('click', (e) => {
    e.stopPropagation();
  });
  
  title.addEventListener('input', () => {
    if (saveTimeout) {
      clearTimeout(saveTimeout);
    }
    
    saveTimeout = setTimeout(async () => {
      const newTitle = title.textContent.trim() || 'Без названия';
      if (newTitle === originalTitle) return;
      
      try {
        const res = await fetch(`/api/notes/${note.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: newTitle }),
        });
        
        if (!res.ok) {
          throw new Error(await res.text());
        }
        
        originalTitle = newTitle;
        const updated = new Date();
        const meta = article.querySelector('.note-card__meta');
        if (meta) {
          meta.textContent = formatDate(updated);
        }
      } catch (error) {
        console.error('Failed to update note title', error);
        title.textContent = originalTitle;
      }
    }, 1000);
  });
  
  title.addEventListener('blur', () => {
    if (saveTimeout) {
      clearTimeout(saveTimeout);
      saveTimeout = null;
    }
    
    const newTitle = title.textContent.trim() || 'Без названия';
    if (newTitle !== originalTitle) {
      (async () => {
        try {
          const res = await fetch(`/api/notes/${note.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle }),
          });
          
          if (!res.ok) {
            throw new Error(await res.text());
          }
          
          originalTitle = newTitle;
          const updated = new Date();
          const meta = article.querySelector('.note-card__meta');
          if (meta) {
            meta.textContent = formatDate(updated);
          }
        } catch (error) {
          console.error('Failed to update note title', error);
          title.textContent = originalTitle;
        }
      })();
    }
  });
  
  title.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      title.blur();
    }
    if (e.key === 'Escape') {
      title.textContent = originalTitle;
      title.blur();
    }
  });

  // Превью контента
  const preview = document.createElement('p');
  preview.className = 'note-card__preview';
  const previewText = getPreviewText(note);
  preview.textContent = previewText || 'Пустая заметка';

  // Футер с метой и кнопкой
  const footer = document.createElement('div');
  footer.className = 'note-card__footer';

  const meta = document.createElement('span');
  meta.className = 'note-card__meta';
  const updated = new Date(note.updatedAt || note.updated_at || Date.now());
  meta.textContent = formatDate(updated);

  const deleteBtn = document.createElement('button');
  deleteBtn.type = 'button';
  deleteBtn.className = 'note-card__delete';
  deleteBtn.setAttribute('aria-label', 'Удалить заметку');
  deleteBtn.title = 'Удалить заметку';
  deleteBtn.textContent = '×';

  deleteBtn.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();

    const confirmed = await confirmDeleteNote(note.title || 'Без названия');
    if (!confirmed) return;

    deleteBtn.disabled = true;
    try {
      const res = await fetch(`/api/notes/${note.id}`, { method: 'DELETE' });
      if (!res.ok) {
        throw new Error(await res.text());
      }

      if (typeof onDeleted === 'function') {
        onDeleted(note.id);
      } else {
        article.remove();
      }
    } catch (error) {
      console.error('Failed to delete note', error);
      window.alert('Не удалось удалить заметку. Попробуйте ещё раз.');
    } finally {
      deleteBtn.disabled = false;
    }
  });

  footer.append(meta, deleteBtn);

  article.append(title, preview, footer);
  return article;
}

function confirmDeleteNote(title) {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';

    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-label', 'Подтверждение удаления');

    const heading = document.createElement('h3');
    heading.className = 'confirm-dialog__title';
    heading.textContent = 'Удалить заметку?';

    const message = document.createElement('p');
    message.className = 'confirm-dialog__text';
    message.textContent = `Заметка «${title}» будет удалена безвозвратно.`;

    const actions = document.createElement('div');
    actions.className = 'confirm-dialog__actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'confirm-dialog__btn confirm-dialog__btn--ghost';
    cancelBtn.textContent = 'Отменить';

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = 'confirm-dialog__btn confirm-dialog__btn--danger';
    confirmBtn.textContent = 'Удалить';

    let closed = false;
    const cleanup = (result) => {
      if (closed) return;
      closed = true;
      document.removeEventListener('keydown', onKeydown);
      overlay.remove();
      resolve(result);
    };

    const onKeydown = (event) => {
      if (event.key === 'Escape') {
        cleanup(false);
      }
    };

    cancelBtn.addEventListener('click', () => cleanup(false));
    confirmBtn.addEventListener('click', () => cleanup(true));
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) {
        cleanup(false);
      }
    });

    actions.append(cancelBtn, confirmBtn);
    dialog.append(heading, message, actions);
    overlay.append(dialog);
    document.body.append(overlay);
    document.addEventListener('keydown', onKeydown);

    requestAnimationFrame(() => {
      overlay.classList.add('is-visible');
      cancelBtn.focus();
    });
  });
}

function formatDate(date) {
  const now = new Date();
  const diff = now - date;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Только что';
  if (minutes < 60) return `${minutes} мин. назад`;
  if (hours < 24) return `${hours} ч. назад`;
  if (days < 7) return `${days} дн. назад`;
  
  return date.toLocaleDateString('ru-RU', { 
    day: 'numeric', 
    month: 'short'
  });
}

function getPreviewText(note) {
  if (!note.blocks || !note.blocks.length) return '';
  
  for (const block of note.blocks) {
    if (block.type === 'text' && block.content) {
      // Убираем HTML теги и берём первые 100 символов
      const text = block.content.replace(/<[^>]*>/g, '').trim();
      if (text) {
        return text.length > 80 ? text.slice(0, 80) + '…' : text;
      }
    }
  }
  
  // Если нет текста, показываем тип контента
  const types = note.blocks.map(b => b.type);
  if (types.includes('image')) return '🖼 Изображение';
  if (types.includes('pdf')) return '📄 PDF документ';
  if (types.includes('audio')) return '🎵 Аудио';
  if (types.includes('video')) return '🎬 Видео';
  if (types.includes('youtube')) return '▶ YouTube';
  if (types.includes('instagram')) return '📸 Instagram Reel';
  if (types.includes('tiktok')) return '🎵 TikTok';
  
  return '';
}
