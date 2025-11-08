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
  el.dataset.placeholder = 'Текст';
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
  figure.appendChild(img);
  if (data.caption) {
    const figcaption = document.createElement('figcaption');
    figcaption.textContent = data.caption;
    figure.appendChild(figcaption);
  }
  return figure;
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
