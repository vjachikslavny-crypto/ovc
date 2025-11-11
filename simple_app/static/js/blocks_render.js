const THEMES = {
  clean: 'theme-clean',
  brief: 'theme-brief',
};

export function renderNote(container, note, theme = 'clean') {
  container.innerHTML = '';
  const blocks = Array.isArray(note?.blocks) ? note.blocks : [];

  blocks.forEach((block) => {
    const element = renderBlock(block);
    if (element) {
      element.dataset.blockId = block.id || '';
      element.dataset.blockType = block.type || '';
      container.appendChild(element);
    }
  });

  const themeClass = THEMES[theme] || THEMES.clean;
  container.dataset.theme = theme;
  container.classList.remove(...Object.values(THEMES));
  container.classList.add(themeClass);
}

export function renderBlock(block) {
  const type = block?.type;
  const data = block?.data || {};

  switch (type) {
    case 'heading':
      return renderHeading(data);
    case 'paragraph':
      return renderParagraph(data);
    case 'bulletList':
      return renderList(data, 'ul');
    case 'numberList':
      return renderList(data, 'ol');
    case 'quote':
      return renderQuote(data);
    case 'table':
      return renderTable(data);
    case 'image':
      return renderImage(data);
    case 'doc':
      return renderDoc(data);
    case 'source':
      return renderSource(data);
    case 'summary':
      return renderSummary(data);
    case 'todo':
      return renderTodo(data);
    case 'divider':
      return renderDivider();
    default:
      return renderParagraph({ parts: [{ text: data?.text || '' }] });
  }
}

const PLACEHOLDER_TEXT = new Set(['Новый заголовок', 'Новый абзац']);

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[exponent]}`;
}

function renderHeading(data) {
  const level = Math.min(Math.max(parseInt(data.level ?? 1, 10), 1), 3);
  const el = document.createElement(`h${level + 1}`);
  el.textContent = sanitizePlaceholder(data.text || '');
  el.className = 'note-block note-block--heading';
  el.contentEditable = 'true';
  el.spellcheck = false;
  el.dataset.placeholder = 'Заголовок';
  return markEditable(el);
}

function renderParagraph(data) {
  const el = document.createElement('p');
  el.className = 'note-block note-block--paragraph';
  el.contentEditable = 'true';
  el.spellcheck = true;
  // Определяем placeholder в зависимости от того, пустой ли блок
  const isEmpty = !data.parts || data.parts.length === 0 || 
    (data.parts.length === 1 && (!data.parts[0].text || data.parts[0].text.trim() === ''));
  el.dataset.placeholder = isEmpty ? 'Начните писать заметку...' : 'Текст';
  const parts = Array.isArray(data.parts)
    ? data.parts.map((part) => ({
        ...part,
        text: sanitizePlaceholder(part.text || ''),
      }))
    : [{ text: sanitizePlaceholder(data.text || '') }];
  parts.forEach((part) => {
    const span = document.createElement('span');
    span.textContent = part.text || '';
    const a = part.annotations || {};
    if (a.bold) span.classList.add('rt-bold');
    if (a.italic) span.classList.add('rt-italic');
    if (a.underline) span.classList.add('rt-underline');
    if (a.strike) span.classList.add('rt-strike');
    if (a.code) span.classList.add('rt-code');
    if (a.href) {
      const link = document.createElement('a');
      link.href = a.href;
      link.rel = 'noreferrer';
      link.target = '_blank';
      link.textContent = span.textContent;
      if (span.className) link.className = span.className;
      el.appendChild(link);
    } else {
      el.appendChild(span);
    }
  });
  return markEditable(el);
}

function sanitizePlaceholder(value) {
  if (!value) return '';
  const trimmed = value.trim();
  if (PLACEHOLDER_TEXT.has(trimmed)) {
    return '';
  }
  return value;
}

function renderList(data, tag) {
  const el = document.createElement(tag);
  el.className = 'note-block note-block--list';
  (data.items || []).forEach((item) => {
    const li = document.createElement('li');
    if (typeof item === 'string') {
      li.textContent = item;
    } else {
      li.textContent = item.text || '';
    }
    el.appendChild(li);
  });
  el.contentEditable = 'true';
  return markEditable(el);
}

function renderQuote(data) {
  const figure = document.createElement('figure');
  figure.className = 'note-block note-block--quote';
  const blockquote = document.createElement('blockquote');
  blockquote.textContent = data.text || '';
  figure.appendChild(blockquote);
  if (data.cite) {
    const figcaption = document.createElement('figcaption');
    figcaption.textContent = data.cite;
    figure.appendChild(figcaption);
  }
  figure.contentEditable = 'true';
  return markEditable(figure);
}

function renderTable(data) {
  const table = document.createElement('table');
  table.className = 'note-block note-block--table ovc-block';
  table.setAttribute('data-block-role', 'table');
  const rows = Array.isArray(data.rows) && data.rows.length ? data.rows : [['', ''], ['', '']];

  rows.forEach((row, rowIdx) => {
    const tr = document.createElement('tr');
    (row || []).forEach((cell, colIdx) => {
      const td = document.createElement('td');
      td.className = 'ovc-block-content table-cell';
      td.contentEditable = 'true';
      td.spellcheck = false;
      td.dataset.row = String(rowIdx);
      td.dataset.col = String(colIdx);
      td.textContent = cell ?? '';
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });

  return table;
}

function renderImage(data) {
  const figure = document.createElement('figure');
  figure.className = 'note-block note-block--image';
  const img = document.createElement('img');
  img.src = data.src || '';
  img.alt = data.alt || '';
  img.loading = 'lazy';
  img.decoding = 'async';
  figure.appendChild(img);
  if (data.caption) {
    const figcaption = document.createElement('figcaption');
    figcaption.textContent = data.caption;
    figure.appendChild(figcaption);
  }
  return figure;
}

function renderDoc(data) {
  // OVC: pdf - поддержка двух режимов просмотра (cover/inline)
  const view = data.view || 'cover';
  const isPdf = data.kind === 'pdf';
  // Извлекаем file_id из URL вида /files/{file_id}/original
  const fileId = data.src ? data.src.match(/\/files\/([^\/]+)/)?.[1] : null;
  const pages = data.meta?.pages || 0;
  
  const card = document.createElement('article');
  card.className = 'note-block note-block--doc';
  if (isPdf) {
    card.classList.add('doc-block--pdf');
    if (fileId) card.dataset.fileId = fileId;
    if (pages) card.dataset.pages = String(pages);
    card.dataset.view = view;
  }

  // Toolbar для PDF (виден только для PDF)
  if (isPdf) {
    const toolbar = document.createElement('div');
    toolbar.className = 'doc-toolbar';
    
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'doc-btn';
    toggleBtn.dataset.action = 'toggle-view';
    toggleBtn.textContent = view === 'cover' ? 'Просмотр' : 'Свернуть';
    
    toolbar.appendChild(toggleBtn);
    card.appendChild(toolbar);
  }

  // Обложка/preview (для PDF используем doc-cover, для других - doc-preview)
  if (isPdf) {
    const cover = document.createElement('div');
    cover.className = 'doc-cover';
    if (view === 'inline') cover.hidden = true;
    
    if (data.preview) {
      const img = document.createElement('img');
      img.src = data.preview;
      img.alt = 'Превью документа';
      img.loading = 'lazy';
      cover.appendChild(img);
    } else {
      const badge = document.createElement('div');
      badge.className = 'doc-preview__badge';
      badge.textContent = (data.kind || 'DOC').toUpperCase();
      cover.appendChild(badge);
    }
    card.appendChild(cover);
  } else {
    // Для не-PDF блоков используем старую структуру с doc-preview
    const preview = document.createElement('div');
    preview.className = 'doc-preview';
    if (data.preview) {
      const img = document.createElement('img');
      img.src = data.preview;
      img.alt = 'Превью документа';
      img.loading = 'lazy';
      preview.appendChild(img);
    } else {
      const badge = document.createElement('div');
      badge.className = 'doc-preview__badge';
      badge.textContent = (data.kind || 'DOC').toUpperCase();
      preview.appendChild(badge);
    }
    card.appendChild(preview);
  }

  // Контейнер для страниц PDF (только для PDF в режиме inline)
  if (isPdf) {
    const pagesContainer = document.createElement('div');
    pagesContainer.className = 'pdf-pages';
    if (view !== 'inline') pagesContainer.hidden = true;
    card.appendChild(pagesContainer);
  }

  // Метаданные и действия (всегда видимы в конце)
  const body = document.createElement('div');
  body.className = 'doc-meta';
  const title = document.createElement('h4');
  title.textContent = data.title || (data.kind === 'pdf' ? 'PDF-документ' : 'Документ');
  const meta = document.createElement('p');
  meta.className = 'doc-meta__info';
  const info = [];
  if (data.meta?.pages) info.push(`${data.meta.pages} стр.`);
  if (data.meta?.size) info.push(formatBytes(data.meta.size));
  if (data.kind) info.push(data.kind.toUpperCase());
  meta.textContent = info.join(' · ') || 'Прикреплённый файл';

  const actions = document.createElement('div');
  actions.className = 'doc-actions';
  if (data.src) {
    const link = document.createElement('a');
    link.href = data.src;
    link.target = '_blank';
    link.rel = 'noreferrer';
    link.textContent = 'Открыть оригинал';
    link.className = 'pill-button pill-button--compact doc-actions__open';
    actions.appendChild(link);
  }

  body.appendChild(title);
  body.appendChild(meta);
  body.appendChild(actions);

  // Метаданные всегда в конце
  card.appendChild(body);
  
  return card;
}

function renderSource(data) {
  const card = document.createElement('article');
  card.className = 'note-block note-block--source';
  const title = document.createElement('h4');
  title.textContent = data.title || data.url || 'Источник';
  const meta = document.createElement('p');
  meta.className = 'source-meta';
  meta.textContent = `${data.domain || ''}${data.published_at ? ' · ' + data.published_at : ''}`;
  const summary = document.createElement('p');
  summary.className = 'source-summary';
  summary.textContent = data.summary || '';
  const link = document.createElement('a');
  link.href = data.url || '#';
  link.textContent = 'Открыть';
  link.target = '_blank';
  link.rel = 'noreferrer';
  card.append(title, meta, summary, link);
  return card;
}

function renderSummary(data) {
  const section = document.createElement('section');
  section.className = 'note-block note-block--summary';
  const title = document.createElement('h4');
  title.textContent = `Сводка · ${data.dateISO || ''}`;
  const body = document.createElement('p');
  body.textContent = data.text || '';
  section.append(title, body);
  section.contentEditable = 'true';
  return markEditable(section);
}

function renderTodo(data) {
  const list = document.createElement('ul');
  list.className = 'note-block note-block--todo';
  (data.items || []).forEach((item) => {
    const li = document.createElement('li');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = Boolean(item.done);
    checkbox.disabled = true;
    const label = document.createElement('span');
    label.textContent = item.text || '';
    li.append(checkbox, label);
    list.appendChild(li);
  });
  list.contentEditable = 'true';
  return markEditable(list);
}

function renderDivider() {
  const hr = document.createElement('hr');
  hr.className = 'note-block note-block--divider';
  return hr;
}

function markEditable(element) {
  if (!element) return element;
  element.classList.add('ovc-block', 'ovc-block-content', 'note-editable');
  if (!element.hasAttribute('contenteditable')) {
    element.setAttribute('contenteditable', 'true');
  }
  return element;
}
