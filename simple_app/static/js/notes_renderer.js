export function renderNoteCard(note) {
  const article = document.createElement('article');
  article.className = 'note-card';
  article.dataset.noteId = note.id;

  const title = document.createElement('h2');
  title.contentEditable = true;
  title.spellcheck = false;
  title.textContent = note.title || 'Без названия';
  title.className = 'note-card__title';
  
  let saveTimeout = null;
  let originalTitle = note.title || 'Без названия';
  
  title.addEventListener('input', () => {
    // Сбрасываем предыдущий таймаут
    if (saveTimeout) {
      clearTimeout(saveTimeout);
    }
    
    // Устанавливаем новый таймаут для сохранения через 1 секунду после окончания ввода
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
        // Обновляем дату обновления в мета
        const updated = new Date();
        const meta = article.querySelector('.note-card__meta');
        if (meta) {
          meta.textContent = `Обновлено ${updated.toLocaleString()}`;
        }
      } catch (error) {
        console.error('Failed to update note title', error);
        // Восстанавливаем оригинальное название при ошибке
        title.textContent = originalTitle;
      }
    }, 1000);
  });
  
  title.addEventListener('blur', () => {
    // Сохраняем сразу при потере фокуса, если есть изменения
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
          // Обновляем дату обновления в мета
          const updated = new Date();
          const meta = article.querySelector('.note-card__meta');
          if (meta) {
            meta.textContent = `Обновлено ${updated.toLocaleString()}`;
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

  const meta = document.createElement('p');
  meta.className = 'note-card__meta';
  const updated = new Date(note.updatedAt || note.updated_at || Date.now());
  meta.textContent = `Обновлено ${updated.toLocaleString()}`;

  const style = document.createElement('span');
  style.className = 'note-card__style';
  style.textContent = note.styleTheme === 'brief' ? 'Brief' : 'Clean';

  const open = document.createElement('a');
  open.href = `/notes/${note.id}`;
  open.className = 'pill-button';
  open.textContent = 'Открыть';

  article.append(title, meta, style, open);
  return article;
}
