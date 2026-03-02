const wordContentCache = new Map();

export function initWordViewers(container, onBlockUpdate) {
  const wordBlocks = container.querySelectorAll('.doc-block--word');
  wordBlocks.forEach((block) => {
    if (block.dataset.wordViewerInitialized === 'true') return;
    block.dataset.wordViewerInitialized = 'true';
    hydrateWordBlock(block, onBlockUpdate);
  });
}

function sanitizeWordHtml(html) {
  if (!html) return '';
  if (window.DOMPurify?.sanitize) {
    return window.DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  }
  // Без DOMPurify показываем как текст, чтобы не вставлять потенциально опасный HTML.
  return escapeHtml(html);
}

function hydrateWordBlock(block, onBlockUpdate) {
  const blockId = block.dataset.blockId;
  const fileId = block.dataset.fileId;
  if (!blockId || !fileId) return;

  const cover = block.querySelector('.doc-cover');
  const inlineContainer = block.querySelector('.word-inline');
  const toggleBtn = block.querySelector('[data-action="toggle-view"]');
  const toTopBtn = block.querySelector('[data-action="to-top"]');
  if (!inlineContainer || !toggleBtn) return;

  let loaded = inlineContainer.dataset.loaded === 'true';
  let loading = false;

  toggleBtn.addEventListener('click', () => {
    const nextView = block.dataset.view === 'inline' ? 'cover' : 'inline';
    setView(nextView);
    if (typeof onBlockUpdate === 'function') {
      onBlockUpdate(blockId, { view: nextView });
    }
  });

  if (toTopBtn) {
    toTopBtn.addEventListener('click', () => {
      inlineContainer.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  function setView(nextView) {
    block.dataset.view = nextView;
    toggleBtn.textContent = nextView === 'inline' ? 'Свернуть' : 'Просмотр';
    if (cover) cover.hidden = nextView === 'inline';
    inlineContainer.hidden = nextView !== 'inline';
    if (toTopBtn) {
      toTopBtn.disabled = nextView !== 'inline';
    }
    if (nextView === 'inline' && !loaded && !loading) {
      loadDocument();
    }
  }

  async function loadDocument() {
    loading = true;
    showPlaceholder();
    if (wordContentCache.has(fileId)) {
      inlineContainer.innerHTML = sanitizeWordHtml(wordContentCache.get(fileId));
      decorateInlineContent(inlineContainer);
      loaded = true;
      inlineContainer.dataset.loaded = 'true';
      loading = false;
      return;
    }
    try {
      const response = await fetch(`/files/${fileId}/doc.html`, {
        headers: { Accept: 'text/html' },
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const html = await response.text();
      const sanitizedHtml = sanitizeWordHtml(html);
      wordContentCache.set(fileId, sanitizedHtml);
      inlineContainer.innerHTML = sanitizedHtml;
      decorateInlineContent(inlineContainer);
      loaded = true;
      inlineContainer.dataset.loaded = 'true';
    } catch (error) {
      inlineContainer.innerHTML = `
        <div class="word-inline__error">
          Не удалось загрузить документ.<br />
          <small>${escapeHtml(error?.message || 'Попробуйте позже')}</small>
        </div>
      `;
    } finally {
      loading = false;
    }
  }

  function showPlaceholder() {
    inlineContainer.innerHTML = `
      <div class="word-inline__placeholder">
        <div class="word-inline__spinner"></div>
        <p>Загружаем документ...</p>
      </div>
    `;
  }

  function decorateInlineContent(root) {
    root.querySelectorAll('a').forEach((link) => {
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'nofollow noopener noreferrer');
    });
    root.querySelectorAll('img').forEach((img) => {
      img.loading = 'lazy';
    });
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, (char) => {
      const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
      };
      return map[char] || char;
    });
  }

  setView(block.dataset.view || 'cover');
}
