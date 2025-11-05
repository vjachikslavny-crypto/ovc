export function renderNoteCard(note) {
  const article = document.createElement('article');
  article.className = 'note-card';
  article.dataset.noteId = note.id;

  const title = document.createElement('h2');
  title.textContent = note.title || 'Без названия';

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
