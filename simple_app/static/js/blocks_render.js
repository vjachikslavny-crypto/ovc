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
    case 'slides':
      return renderSlides(data);
    case 'audio':
      return renderAudio(data);
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

function renderTable(data = {}) {
  if (data.kind && data.summary) {
    return renderExcelTable(data);
  }

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

const TABLE_KIND_LABELS = {
  xlsx: 'Excel (.xlsx)',
  xls: 'Excel (.xls)',
  csv: 'CSV',
};

function renderExcelTable(data) {
  const wrapper = document.createElement('section');
  wrapper.className = 'note-block table-block table-block--excel';
  const view = data.view || 'cover';
  wrapper.dataset.view = view;
  if (data.kind) wrapper.dataset.kind = data.kind;
  if (data.summary) wrapper.dataset.summaryUrl = data.summary;
  if (data.src) wrapper.dataset.src = data.src;
  const activeSheet = data.activeSheet || data.active_sheet;
  if (activeSheet) wrapper.dataset.activeSheet = activeSheet;
  const fileIdMatch = data.src?.match(/\/files\/([^/]+)/);
  if (fileIdMatch) wrapper.dataset.fileId = fileIdMatch[1];
  // OVC: excel - диаграммы отключены, фокус на предпросмотре таблиц

  const toolbar = document.createElement('div');
  toolbar.className = 'table-toolbar';
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'pill-button';
  toggleBtn.dataset.action = 'toggle-view';
  toggleBtn.textContent = view === 'inline' ? 'Свернуть' : 'Просмотр';
  toolbar.appendChild(toggleBtn);
  const spacer = document.createElement('div');
  spacer.className = 'spacer';
  toolbar.appendChild(spacer);
  if (data.src) {
    const downloadOriginal = document.createElement('a');
    downloadOriginal.className = 'pill-button pill-button--ghost';
    downloadOriginal.href = data.src;
    downloadOriginal.target = '_blank';
    downloadOriginal.rel = 'noopener';
    downloadOriginal.dataset.role = 'download-original';
    downloadOriginal.textContent = 'Скачать файл';
    toolbar.appendChild(downloadOriginal);
  }
  wrapper.appendChild(toolbar);

  const cover = document.createElement('div');
  cover.className = 'table-cover';
  cover.dataset.role = 'cover';
  if (view === 'inline') cover.hidden = true;

  const coverIcon = document.createElement('div');
  coverIcon.className = 'table-cover-icon';
  coverIcon.textContent = data.kind === 'csv' ? '🧾' : '📊';
  cover.appendChild(coverIcon);

  const coverBody = document.createElement('div');
  coverBody.className = 'table-cover-body';

  const kindLabel = document.createElement('p');
  kindLabel.className = 'table-cover-kind';
  kindLabel.textContent = TABLE_KIND_LABELS[data.kind] || 'Таблица';
  coverBody.appendChild(kindLabel);

  const info = document.createElement('p');
  info.className = 'table-cover-info';
  info.dataset.role = 'cover-info';
  info.textContent = 'Загружаем метаданные…';
  coverBody.appendChild(info);

  const preview = document.createElement('div');
  preview.className = 'table-cover-preview';
  preview.dataset.role = 'preview-table';
  coverBody.appendChild(preview);

  cover.appendChild(coverBody);
  wrapper.appendChild(cover);

  const inline = document.createElement('div');
  inline.className = 'table-inline';
  inline.dataset.role = 'inline';
  if (view !== 'inline') inline.hidden = true;

  const inlineToolbar = document.createElement('div');
  inlineToolbar.className = 'table-inline-toolbar';

  // Кнопки переключения листов
  const sheetNav = document.createElement('div');
  sheetNav.className = 'table-sheet-nav';
  const prevSheetBtn = document.createElement('button');
  prevSheetBtn.type = 'button';
  prevSheetBtn.className = 'pill-button pill-button--ghost';
  prevSheetBtn.dataset.action = 'prev-sheet';
  prevSheetBtn.textContent = '◀';
  prevSheetBtn.setAttribute('aria-label', 'Предыдущий лист');
  prevSheetBtn.disabled = true;
  sheetNav.appendChild(prevSheetBtn);

  const sheetSelect = document.createElement('select');
  sheetSelect.dataset.role = 'sheet-select';
  sheetSelect.disabled = true;
  sheetSelect.setAttribute('aria-label', 'Выбор листа');
  const loadingOption = document.createElement('option');
  loadingOption.textContent = 'Загрузка…';
  sheetSelect.appendChild(loadingOption);
  sheetNav.appendChild(sheetSelect);

  const nextSheetBtn = document.createElement('button');
  nextSheetBtn.type = 'button';
  nextSheetBtn.className = 'pill-button pill-button--ghost';
  nextSheetBtn.dataset.action = 'next-sheet';
  nextSheetBtn.textContent = '▶';
  nextSheetBtn.setAttribute('aria-label', 'Следующий лист');
  nextSheetBtn.disabled = true;
  sheetNav.appendChild(nextSheetBtn);

  inlineToolbar.appendChild(sheetNav);
  // OVC: excel - поиск по окну убран (работал только для загруженных 200 строк, путал пользователей)

  // OVC: excel - кнопка переноса убрана

  const downloadSheet = document.createElement('a');
  downloadSheet.className = 'pill-button pill-button--ghost';
  downloadSheet.dataset.role = 'download-sheet';
  downloadSheet.href = '#';
  downloadSheet.download = '';  // Подсказка браузеру, что это скачивание
  downloadSheet.textContent = 'Скачать CSV';
  inlineToolbar.appendChild(downloadSheet);

  inline.appendChild(inlineToolbar);

  const inlineBody = document.createElement('div');
  inlineBody.className = 'table-inline-body';
  const tableScroll = document.createElement('div');
  tableScroll.className = 'table-scroll';
  const dataTable = document.createElement('table');
  dataTable.className = 'data-grid';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  headRow.dataset.role = 'columns';
  thead.appendChild(headRow);
  const tbody = document.createElement('tbody');
  tbody.dataset.role = 'rows';
  dataTable.appendChild(thead);
  dataTable.appendChild(tbody);
  tableScroll.appendChild(dataTable);
  inlineBody.appendChild(tableScroll);

  const emptyState = document.createElement('div');
  emptyState.className = 'table-empty';
  emptyState.dataset.role = 'empty-state';
  emptyState.hidden = true;
  const emptyText = document.createElement('p');
  emptyText.textContent = 'Нет данных для отображения';
  emptyState.appendChild(emptyText);
  inlineBody.appendChild(emptyState);

  inline.appendChild(inlineBody);

  // OVC: excel - footer с пагинацией полностью убран (не нужен для большинства файлов)

  // OVC: excel - диаграммы отключены, фокус на предпросмотре таблиц

  wrapper.appendChild(inline);
  return wrapper;
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
  const view = data.view || 'cover';
  const kind = data.kind || 'doc';
  const isPdf = kind === 'pdf';
  const isWord = kind === 'docx' || kind === 'rtf';
  const supportsInline = isPdf || isWord;
  const fileId = data.src ? data.src.match(/\/files\/([^/]+)/)?.[1] : null;

  const card = document.createElement('article');
  card.className = 'note-block note-block--doc';
  card.dataset.view = view;
  if (fileId) card.dataset.fileId = fileId;
  if (data.meta?.pages) card.dataset.pages = String(data.meta.pages);

  if (isPdf) {
    card.classList.add('doc-block--pdf');
  }
  if (isWord) {
    card.classList.add('doc-block--word');
    card.dataset.kind = kind;
  }

  if (supportsInline) {
    const toolbar = document.createElement('div');
    toolbar.className = 'doc-toolbar';

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'doc-btn';
    toggleBtn.dataset.action = 'toggle-view';
    toggleBtn.textContent = view === 'cover' ? 'Просмотр' : 'Свернуть';
    toolbar.appendChild(toggleBtn);

    if (isWord) {
      const spacer = document.createElement('div');
      spacer.className = 'spacer';
      toolbar.appendChild(spacer);

      const toTopBtn = document.createElement('button');
      toTopBtn.className = 'doc-btn';
      toTopBtn.dataset.action = 'to-top';
      toTopBtn.textContent = 'Вверх';
      toTopBtn.disabled = view !== 'inline';
      toolbar.appendChild(toTopBtn);
    }

    card.appendChild(toolbar);
  }

  if (supportsInline) {
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
      // OVC: docx - для Word файлов показываем информативный бейдж вместо превью
      const badge = document.createElement('div');
      badge.className = 'doc-preview__badge';
      
      if (isWord) {
        // Для Word файлов показываем название и информацию
        const title = document.createElement('div');
        title.className = 'doc-badge__title';
        title.textContent = data.title || 'Документ Word';
        badge.appendChild(title);
        
        if (data.meta?.words) {
          const words = document.createElement('div');
          words.className = 'doc-badge__meta';
          words.textContent = `${data.meta.words} слов`;
          badge.appendChild(words);
        }
        
        const type = document.createElement('div');
        type.className = 'doc-badge__type';
        type.textContent = kind.toUpperCase();
        badge.appendChild(type);
      } else {
        badge.textContent = kind.toUpperCase();
      }
      
      cover.appendChild(badge);
    }
    card.appendChild(cover);
  } else {
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
      badge.textContent = kind.toUpperCase();
      preview.appendChild(badge);
    }
    card.appendChild(preview);
  }

  if (isPdf) {
    const pagesContainer = document.createElement('div');
    pagesContainer.className = 'pdf-pages';
    if (view !== 'inline') pagesContainer.hidden = true;
    card.appendChild(pagesContainer);
  }

  if (isWord) {
    const inlineContainer = document.createElement('div');
    inlineContainer.className = 'word-inline';
    inlineContainer.hidden = view !== 'inline';
    inlineContainer.dataset.loaded = 'false';
    inlineContainer.innerHTML = `
      <div class="word-inline__placeholder">
        <div class="word-inline__spinner"></div>
        <p>Загружаем документ...</p>
      </div>
    `;
    card.appendChild(inlineContainer);
  }

  const body = document.createElement('div');
  body.className = 'doc-meta';
  const title = document.createElement('h4');
  title.textContent = data.title || (isPdf ? 'PDF-документ' : 'Документ');
  const meta = document.createElement('p');
  meta.className = 'doc-meta__info';
  const info = [];
  if (data.meta?.pages) info.push(`${data.meta.pages} стр.`);
  if (data.meta?.words) info.push(`${data.meta.words} слов`);
  if (data.meta?.size) info.push(formatBytes(data.meta.size));
  if (kind) info.push(kind.toUpperCase());
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
  card.appendChild(body);

  return card;
}

function renderSlides(data) {
  const view = data.view || 'cover';
  const block = document.createElement('article');
  block.className = 'slides-block';
  block.dataset.view = view;
  const fileId = data.src ? data.src.match(/\/files\/([^/]+)/)?.[1] : null;
  if (fileId) block.dataset.fileId = fileId;
  if (data.slides) block.dataset.slidesMeta = data.slides;
  if (data.count) block.dataset.count = String(data.count);
  if (data.preview) block.dataset.preview = data.preview;

  const toolbar = document.createElement('div');
  toolbar.className = 'slides-toolbar';
  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'pill-button';
  toggleBtn.dataset.action = 'toggle-view';
  toggleBtn.textContent = view === 'inline' ? 'Свернуть' : 'Просмотр';
  toolbar.appendChild(toggleBtn);
  const spacer = document.createElement('div');
  spacer.className = 'spacer';
  toolbar.appendChild(spacer);
  const fullBtn = document.createElement('button');
  fullBtn.className = 'icon-button';
  fullBtn.dataset.action = 'fullscreen';
  fullBtn.textContent = '⛶';
  fullBtn.setAttribute('aria-label', 'Во весь экран');
  toolbar.appendChild(fullBtn);
  block.appendChild(toolbar);

  const cover = document.createElement('div');
  cover.className = 'slides-cover';
  if (view === 'inline') cover.hidden = true;
  if (data.preview) {
    const img = document.createElement('img');
    img.className = 'slides-cover-img';
    img.src = data.preview;
    img.alt = 'Обложка презентации';
    img.loading = 'lazy';
    cover.appendChild(img);
  } else {
    const badge = document.createElement('div');
    badge.className = 'slides-cover-placeholder';
    badge.textContent = 'PPTX';
    cover.appendChild(badge);
  }
  const countBadge = document.createElement('div');
  countBadge.className = 'slides-count-badge';
  countBadge.textContent = `${data.count || '?'} слайдов`;
  cover.appendChild(countBadge);
  block.appendChild(cover);

  const inline = document.createElement('div');
  inline.className = 'slides-inline';
  inline.hidden = view !== 'inline';

  // OVC: slides - контейнер для всех слайдов (как в PDF)
  const slidesContainer = document.createElement('div');
  slidesContainer.className = 'slides-pages';
  if (view !== 'inline') slidesContainer.hidden = true;
  inline.appendChild(slidesContainer);

  // OVC: slides - старый режим с одним слайдом и навигацией (оставляем для совместимости)
  const singleView = document.createElement('div');
  singleView.className = 'slides-single-view';
  singleView.hidden = true; // По умолчанию скрыт, показываем все слайды

  const pager = document.createElement('div');
  pager.className = 'slides-pager';
  const prevBtn = document.createElement('button');
  prevBtn.dataset.action = 'prev';
  prevBtn.textContent = '←';
  const indexLabel = document.createElement('span');
  indexLabel.className = 'slides-index';
  const cur = document.createElement('b');
  cur.className = 'cur';
  cur.textContent = '1';
  const total = document.createElement('span');
  total.className = 'total';
  total.textContent = data.count ? String(data.count) : '?';
  indexLabel.append(cur, document.createTextNode('/'), total);
  const nextBtn = document.createElement('button');
  nextBtn.dataset.action = 'next';
  nextBtn.textContent = '→';
  pager.append(prevBtn, indexLabel, nextBtn);
  singleView.appendChild(pager);

  const viewPort = document.createElement('div');
  viewPort.className = 'slides-view';
  const img = document.createElement('img');
  img.className = 'slides-image';
  img.alt = 'Слайд презентации';
  img.decoding = 'async';
  viewPort.appendChild(img);
  singleView.appendChild(viewPort);

  const thumbs = document.createElement('div');
  thumbs.className = 'slides-thumbs';
  singleView.appendChild(thumbs);
  inline.appendChild(singleView);

  const placeholder = document.createElement('div');
  placeholder.className = 'slides-placeholder';
  placeholder.textContent = 'Загружаем презентацию...';
  inline.appendChild(placeholder);

  block.appendChild(inline);
  return block;
}

function renderAudio(data) {
  const view = data.view || 'mini';
  const fileId = data.waveform ? data.waveform.match(/\/files\/(.+?)\//)?.[1] : (data.src?.match(/\/files\/(.+?)\//)?.[1] || '');
  const block = document.createElement('article');
  block.className = 'audio-block';
  block.dataset.view = view;
  if (fileId) block.dataset.fileId = fileId;
  if (data.waveform) block.dataset.waveform = data.waveform;
  if (data.duration) block.dataset.duration = String(data.duration);

  const controls = document.createElement('div');
  controls.className = 'audio-controls';

  const playBtn = document.createElement('button');
  playBtn.className = 'audio-btn audio-btn--play';
  playBtn.dataset.action = 'play';
  playBtn.textContent = '▶';
  controls.appendChild(playBtn);

  const timeline = document.createElement('div');
  timeline.className = 'audio-timeline';
  const progress = document.createElement('div');
  progress.className = 'audio-progress';
  timeline.appendChild(progress);
  controls.appendChild(timeline);

  const timeBox = document.createElement('div');
  timeBox.className = 'audio-time';
  const cur = document.createElement('span');
  cur.className = 'audio-time__current';
  cur.textContent = '0:00';
  const sep = document.createTextNode('/');
  const dur = document.createElement('span');
  dur.className = 'audio-time__duration';
  dur.textContent = data.duration ? formatTime(data.duration) : '–:–';
  timeBox.append(cur, sep, dur);
  controls.appendChild(timeBox);

  const toggleView = document.createElement('button');
  toggleView.className = 'audio-btn';
  toggleView.dataset.action = 'toggle-view';
  toggleView.textContent = view === 'expanded' ? '▾' : '▤';
  controls.appendChild(toggleView);

  block.appendChild(controls);

  const audioEl = document.createElement('audio');
  audioEl.preload = 'metadata';
  if (data.src) audioEl.src = data.src;
  // OVC: audio - нормализуем MIME-тип для WebM с codecs
  if (data.mime) {
    // Для WebM с codecs используем базовый тип, браузер сам определит codec
    const normalizedMime = data.mime.includes('webm') && data.mime.includes('codecs') 
      ? 'audio/webm' 
      : data.mime;
    audioEl.type = normalizedMime;
  }
  // Добавляем controls для отладки (можно убрать позже)
  audioEl.controls = false;
  block.appendChild(audioEl);

  const expanded = document.createElement('div');
  expanded.className = 'audio-expanded';
  expanded.hidden = view !== 'expanded';
  const actions = document.createElement('div');
  actions.className = 'audio-actions';

  const rewindBtn = document.createElement('button');
  rewindBtn.className = 'audio-btn';
  rewindBtn.dataset.action = 'rewind-10';
  rewindBtn.textContent = '«10';
  actions.appendChild(rewindBtn);

  const forwardBtn = document.createElement('button');
  forwardBtn.className = 'audio-btn';
  forwardBtn.dataset.action = 'ffwd-10';
  forwardBtn.textContent = '10»';
  actions.appendChild(forwardBtn);

  const downloadBtn = document.createElement('button');
  downloadBtn.className = 'audio-btn';
  downloadBtn.dataset.action = 'download';
  downloadBtn.textContent = '⬇︎';
  if (!data.src) downloadBtn.disabled = true;
  actions.appendChild(downloadBtn);

  expanded.appendChild(actions);
  const transcript = document.createElement('div');
  transcript.className = 'audio-transcript';
  transcript.hidden = !data.transcript;
  if (data.transcript) transcript.textContent = data.transcript;
  expanded.appendChild(transcript);
  block.appendChild(expanded);

  return block;
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

function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '–:–';
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60)
    .toString()
    .padStart(2, '0');
  return `${minutes}:${secs}`;
}
