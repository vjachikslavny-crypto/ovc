const slidesMetaCache = new Map();

export function initSlidesViewers(container, onBlockUpdate) {
  const blocks = container.querySelectorAll('.slides-block');
  blocks.forEach((block) => {
    if (block.dataset.slidesReady === 'true') return;
    block.dataset.slidesReady = 'true';
    setupSlidesBlock(block, onBlockUpdate);
  });
}

function setupSlidesBlock(block, onBlockUpdate) {
  const cover = block.querySelector('.slides-cover');
  const inline = block.querySelector('.slides-inline');
  const slidesContainer = block.querySelector('.slides-pages');
  const toggleBtn = block.querySelector('[data-action="toggle-view"]');
  const fullBtn = block.querySelector('[data-action="fullscreen"]');
  const prevBtn = block.querySelector('[data-action="prev"]');
  const nextBtn = block.querySelector('[data-action="next"]');
  const imageEl = block.querySelector('.slides-image');
  const indexCur = block.querySelector('.slides-index .cur');
  const indexTotal = block.querySelector('.slides-index .total');
  const thumbs = block.querySelector('.slides-thumbs');
  const placeholder = block.querySelector('.slides-placeholder');

  const fileId = block.dataset.fileId;
  const slidesMetaUrl = block.dataset.slidesMeta;
  const preview = block.dataset.preview;

  let meta = { count: parseInt(block.dataset.count || '0', 10) || null };
  let current = 1;
  let loadingMeta = false;

  if (indexTotal && meta.count) {
    indexTotal.textContent = String(meta.count);
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const nextView = block.dataset.view === 'inline' ? 'cover' : 'inline';
      block.dataset.view = nextView;
      toggleBtn.textContent = nextView === 'inline' ? 'Свернуть' : 'Просмотр';
      cover.hidden = nextView === 'inline';
      inline.hidden = nextView !== 'inline';
      
      // OVC: slides - показываем контейнер со всеми слайдами в режиме inline
      if (slidesContainer) {
        slidesContainer.hidden = nextView !== 'inline';
        if (nextView === 'inline' && meta.count && slidesContainer.children.length === 0) {
          // Если слайды еще не загружены, загружаем метаданные и рендерим
          ensureMeta().then(() => {
            if (meta.count) renderAllSlides();
          }).catch(showError);
        }
      }
      
      if (typeof onBlockUpdate === 'function' && block.dataset.blockId) {
        onBlockUpdate(block.dataset.blockId, { view: nextView });
      }
    });
  }

  fullBtn?.addEventListener('click', () => {
    if (!imageEl) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      imageEl.requestFullscreen?.();
    }
  });

  prevBtn?.addEventListener('click', () => {
    if (!meta.count) return;
    current = Math.max(1, current - 1);
    showSlide(current);
  });

  nextBtn?.addEventListener('click', () => {
    if (!meta.count) return;
    current = Math.min(meta.count, current + 1);
    showSlide(current);
  });

  if (block.dataset.view === 'inline') {
    // OVC: slides - в режиме inline показываем все слайды
    ensureMeta().then(() => {
      if (slidesContainer && meta.count) {
        renderAllSlides();
      } else if (imageEl) {
        // Fallback на старый режим, если контейнер отсутствует
        showSlide(current);
      }
    }).catch(showError);
  } else if (preview && imageEl) {
    imageEl.src = preview;
  }

  function ensureMeta() {
    // OVC: pptx - если слайды не были сгенерированы (LibreOffice не установлен), показываем сообщение
    if (!slidesMetaUrl) {
      if (placeholder) placeholder.textContent = 'Слайды не были сгенерированы. Установите LibreOffice для конвертации презентаций.';
      return Promise.reject(new Error('Нет данных по слайдам'));
    }
    if (slidesMetaCache.has(slidesMetaUrl)) {
      meta = slidesMetaCache.get(slidesMetaUrl);
      updateThumbs();
      return Promise.resolve(meta);
    }
    if (loadingMeta) return Promise.resolve(meta);
    loadingMeta = true;
    return fetch(slidesMetaUrl)
      .then((res) => {
        if (res.status === 202) throw new Error('Презентация ещё обрабатывается');
        if (!res.ok) throw new Error('Не удалось загрузить слайды');
        return res.json();
      })
      .then((data) => {
        meta = data || {};
        slidesMetaCache.set(slidesMetaUrl, meta);
        if (indexTotal && meta.count) indexTotal.textContent = String(meta.count);
        updateThumbs();
        placeholder.hidden = true;
        // OVC: slides - если в режиме inline и есть контейнер, рендерим все слайды
        if (block.dataset.view === 'inline' && slidesContainer && meta.count) {
          renderAllSlides();
        }
      })
      .finally(() => {
        loadingMeta = false;
      });
  }

  function showSlide(index) {
    if (!imageEl) return;
    if (!meta.count) {
      if (preview) {
        imageEl.src = preview;
        placeholder.hidden = true;
      }
      return;
    }
    current = Math.min(Math.max(1, index), meta.count);
    placeholder.hidden = true;
    const slideUrl = `/files/${fileId}/slide/${current}`;
    imageEl.src = slideUrl;
    indexCur.textContent = String(current);
    updateThumbHighlight();
  }

  function updateThumbs() {
    if (!thumbs || !meta.count) return;
    thumbs.innerHTML = '';
    const count = meta.count;
    const maxThumbs = Math.min(count, 12);
    for (let i = 1; i <= maxThumbs; i += 1) {
      const thumb = document.createElement('img');
      thumb.className = 'slides-thumb';
      thumb.loading = 'lazy';
      thumb.src = `/files/${fileId}/slide/${i}`;
      thumb.dataset.index = String(i);
      thumb.addEventListener('click', () => {
        current = parseInt(thumb.dataset.index, 10);
        showSlide(current);
      });
      thumbs.appendChild(thumb);
    }
    updateThumbHighlight();
  }

  function updateThumbHighlight() {
    if (!thumbs) return;
    thumbs.querySelectorAll('.slides-thumb').forEach((thumb) => {
      if (thumb.dataset.index === String(current)) {
        thumb.classList.add('active');
      } else {
        thumb.classList.remove('active');
      }
    });
  }

  function renderAllSlides() {
    if (!slidesContainer || !meta.count || !fileId) return;
    
    // Очищаем контейнер
    slidesContainer.innerHTML = '';
    
    // Создаем все слайды
    for (let i = 1; i <= meta.count; i++) {
      const slideWrapper = document.createElement('div');
      slideWrapper.className = 'slides-page';
      
      const img = document.createElement('img');
      img.className = 'slides-page-img';
      img.alt = `Слайд ${i}`;
      img.loading = 'lazy';
      img.dataset.slideNum = String(i);
      img.dataset.src = `/files/${fileId}/slide/${i}`;
      
      // Lazy loading - загружаем только видимые слайды
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            if (!img.src && img.dataset.src) {
              img.src = img.dataset.src;
            }
            observer.unobserve(img);
          }
        });
      }, {
        rootMargin: '200px', // Предзагрузка за 200px до появления
        threshold: 0.1
      });
      
      observer.observe(img);
      
      slideWrapper.appendChild(img);
      slidesContainer.appendChild(slideWrapper);
    }
  }

  function showError(error) {
    if (!placeholder) return;
    placeholder.hidden = false;
    placeholder.textContent = error?.message || 'Не удалось загрузить презентацию';
  }
}
