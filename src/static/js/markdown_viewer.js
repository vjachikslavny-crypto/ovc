const MAX_MD_LINES = 10000;
let parserInstance = null;

export function initMarkdownViewers(container) {
  if (!container) return;
  const blocks = container.querySelectorAll('.note-block--markdown');
  if (!blocks.length) return;

  blocks.forEach((block) => {
    if (block.dataset.mdViewerReady === 'true') return;
    block.dataset.mdViewerReady = 'true';
    setupMarkdownBlock(block);
  });
}

function setupMarkdownBlock(block) {
  const bodyEl = block.querySelector('[data-role="md-body"]');
  const capEl = block.querySelector('[data-role="cap"]');
  const copyBtn = block.querySelector('[data-action="copy"]');
  const expandBtn = block.querySelector('[data-action="expand"]');
  const downloadBtn = block.querySelector('[data-role="download"]');
  const src = block.dataset.src || '';
  const previewUrl = block.dataset.previewUrl || src;
  const filename = block.dataset.filename || '';
  const totalLines = parseInt(block.dataset.lineCount || '0', 10) || null;

  if (downloadBtn && src) {
    downloadBtn.href = src;
    if (filename) {
      downloadBtn.setAttribute('download', filename);
    }
  }

  const state = getBlockState(block);

  copyBtn?.addEventListener('click', async () => {
    if (!state.currentText) return;
    try {
      await navigator.clipboard.writeText(state.currentText);
      copyBtn.textContent = 'Copied';
      setTimeout(() => {
        copyBtn.textContent = 'Copy';
      }, 1600);
    } catch (error) {
      console.warn('Clipboard copy failed', error);
    }
  });

  expandBtn?.addEventListener('click', () => {
    if (!src) return;
    if (!state.expanded) {
      // Разворачиваем - загружаем полный файл
    state.expanded = true;
      expandBtn.textContent = 'Свернуть';
      bodyEl.classList.add('md-expanded');
    fetchMarkdown(block, src, bodyEl, capEl, { clamp: true, totalLines });
    } else {
      // Сворачиваем - возвращаемся к превью
      state.expanded = false;
      expandBtn.textContent = 'Просмотр';
      bodyEl.classList.remove('md-expanded');
      const previewUrl = block.dataset.previewUrl || src;
      if (previewUrl) {
        fetchMarkdown(block, previewUrl, bodyEl, capEl, { clamp: true, preview: true, totalLines });
      }
    }
  });

  if (previewUrl) {
    fetchMarkdown(block, previewUrl, bodyEl, capEl, { clamp: true, preview: true, totalLines });
  }
}

function fetchMarkdown(block, url, bodyEl, capEl, options = {}) {
  if (!url || !bodyEl) return;
  const loadingCls = 'md-block--loading';
  block.classList.add(loadingCls);

  fetch(url)
    .then((res) => {
      const previewTruncated = res.headers.get('X-OVC-MD-Truncated') === 'true';
      return res.text().then((text) => ({ text, previewTruncated }));
    })
    .then(({ text, previewTruncated }) => {
      block.classList.remove(loadingCls);
      if (!text && text !== '') return;
      const { limitedText, truncated, lineCount } = clampLines(text, options.clamp !== false);
      if (options.preview) {
        block.dataset.previewLoaded = 'true';
      }
      block.dataset.renderedLines = String(lineCount);
      const state = getBlockState(block);
      if (state) {
        state.currentText = limitedText;
        if (!options.preview) {
          state.expanded = true;
        }
      }
      renderMarkdownInto(bodyEl, limitedText);
      updateCaption(capEl, {
        preview: Boolean(options.preview),
        previewTruncated,
        truncated,
        totalLines: options.totalLines || lineCount,
        expanded: !options.preview,
      });
    })
    .catch((error) => {
      console.error('Failed to load markdown preview', error);
      block.classList.remove(loadingCls);
      if (bodyEl) {
        bodyEl.textContent = 'Не удалось загрузить Markdown';
      }
      if (capEl) {
        capEl.hidden = false;
        capEl.textContent = 'Ошибка при загрузке Markdown.';
      }
    });
}

function clampLines(text, clamp = true) {
  if (!clamp) {
    return { limitedText: text, truncated: false, lineCount: countLines(text) };
  }
  const lines = text.split(/\r?\n/);
  const truncated = lines.length > MAX_MD_LINES;
  const limited = truncated ? lines.slice(0, MAX_MD_LINES) : lines;
  return {
    limitedText: limited.join('\n'),
    truncated,
    lineCount: lines.length,
  };
}

function countLines(text) {
  if (!text) return 0;
  return text.split(/\r?\n/).length;
}

function renderMarkdownInto(container, rawText) {
  if (!container) return;
  const parser = getMarkdownParser();
  let renderedHTML = '';
  try {
    renderedHTML = parser ? parser.render(rawText || '') : escapeHtml(rawText || '');
  } catch (error) {
    console.error('Markdown parse error', error);
    renderedHTML = escapeHtml(rawText || '');
  }
  const purifier = window.DOMPurify;
  const safeHTML = purifier
    ? purifier.sanitize(renderedHTML, {
        ALLOWED_TAGS: [
          'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'ul', 'ol', 'li',
          'a', 'em', 'strong', 'code', 'pre', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
          'img', 'hr', 'sup', 'sub', 'input', 'span', 'div', 'section', 'figure', 'figcaption'
        ],
        ALLOWED_ATTR: ['href', 'title', 'alt', 'src', 'class', 'target', 'rel', 'checked', 'type'],
        ADD_ATTR: ['loading'],
      })
    : renderedHTML;
  container.innerHTML = safeHTML;
  enhanceRendered(container);
}

function enhanceRendered(container) {
  container.querySelectorAll('a[href^="http"]').forEach((link) => {
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  });
  container.querySelectorAll('img').forEach((img) => {
    img.loading = 'lazy';
  });
  container.querySelectorAll('pre code').forEach((codeBlock) => {
    if (window.Prism && typeof window.Prism.highlightElement === 'function') {
      window.Prism.highlightElement(codeBlock);
    }
  });
}

function escapeHtml(value = '') {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function updateCaption(capEl, { preview, previewTruncated, truncated, totalLines, expanded }) {
  if (!capEl) return;
  capEl.hidden = true;
  if (preview && (previewTruncated || (totalLines && totalLines > MAX_MD_LINES))) {
    capEl.hidden = false;
    capEl.textContent = 'Показан предпросмотр. Нажмите Expand, чтобы увидеть больше.';
    return;
  }
  if (!preview && (truncated || (totalLines && totalLines > MAX_MD_LINES))) {
    capEl.hidden = false;
    const suffix = totalLines ? ` (из ${totalLines})` : '';
    capEl.textContent = `Показаны первые 10 000 строк${suffix}. Скачайте файл, чтобы увидеть всё.`;
  }
}

function getMarkdownParser() {
  if (parserInstance) return parserInstance;
  const base = window.markdownit;
  if (typeof base !== 'function') return null;
  parserInstance = base({
    html: false,
    linkify: true,
    breaks: true,
  });
  if (window.markdownitTaskLists) {
    parserInstance.use(window.markdownitTaskLists, { label: true, labelAfter: true });
  }
  if (window.markdownitSub) {
    parserInstance.use(window.markdownitSub);
  }
  if (window.markdownitSup) {
    parserInstance.use(window.markdownitSup);
  }
  if (window.markdownitFootnote) {
    parserInstance.use(window.markdownitFootnote);
  }
  return parserInstance;
}

const blockStateMap = new WeakMap();
function getBlockState(block) {
  if (!blockStateMap.has(block)) {
    blockStateMap.set(block, { currentText: '', expanded: false });
  }
  return blockStateMap.get(block);
}
