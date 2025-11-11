// OVC: pdf - виджет для просмотра PDF с ленивой подгрузкой страниц

// OVC: pdf - глобальное хранилище для сохранения состояния изображений при перерисовке
const imageStateCache = new Map();

export function initPdfViewers(container, onBlockUpdate) {
  // Инициализируем все PDF-блоки в контейнере
  const pdfBlocks = container.querySelectorAll('.doc-block--pdf');
  console.log('PDF viewer: initPdfViewers called', { blocksCount: pdfBlocks.length, container });
  
  if (pdfBlocks.length === 0) {
    console.log('PDF viewer: no PDF blocks found in container');
    return;
  }
  
  pdfBlocks.forEach((block, index) => {
    // OVC: pdf - проверяем, не инициализирован ли уже блок
    if (block.dataset.pdfViewerInitialized === 'true') {
      console.log('PDF viewer: block already initialized', index);
      return; // Уже инициализирован
    }
    
    const fileId = block.dataset.fileId;
    const pages = block.dataset.pages;
    console.log('PDF viewer: initializing block', { index, fileId, pages, block });
    
    block.dataset.pdfViewerInitialized = 'true';
    initPdfViewer(block, onBlockUpdate);
  });
  }

function initPdfViewer(block, onBlockUpdate) {
  const fileId = block.dataset.fileId;
  const pages = parseInt(block.dataset.pages || '0', 10);
  // OVC: pdf - читаем view из dataset блока (актуальное значение)
  let view = block.dataset.view || 'cover';
  
  console.log('PDF viewer: initPdfViewer started', { 
    fileId, 
    pages, 
    view,
    blockView: block.dataset.view,
    blockId: block.dataset.blockId
  });
  
  if (!fileId || !pages) {
    console.warn('PDF viewer: missing fileId or pages', { fileId, pages, block });
    return;
  }
  
  const toolbar = block.querySelector('.doc-toolbar');
  const cover = block.querySelector('.doc-cover');
  const pagesContainer = block.querySelector('.pdf-pages');
  
  console.log('PDF viewer: elements found', { 
    toolbar: !!toolbar, 
    cover: !!cover, 
    pagesContainer: !!pagesContainer,
    coverHidden: cover?.hidden,
    pagesContainerHidden: pagesContainer?.hidden,
    pagesContainerDisplay: pagesContainer ? window.getComputedStyle(pagesContainer).display : 'none'
  });
  
  if (!toolbar || !cover || !pagesContainer) {
    console.warn('PDF viewer: missing required elements', { toolbar: !!toolbar, cover: !!cover, pagesContainer: !!pagesContainer });
    return;
  }
  
  console.log('PDF viewer initialized', { fileId, pages, view, blockView: block.dataset.view });
  
  let currentZoom = 1.0;
  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = 2.0;
  const ZOOM_STEP = 0.25;
  
  // IntersectionObserver для lazy-load страниц
  const pageObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target.querySelector('img');
        if (img && !img.src && !img.dataset.loading) {
          const pageNum = parseInt(img.dataset.pageNum || '1', 10);
          console.log('PDF viewer: IntersectionObserver triggered for page', pageNum);
          loadPage(img);
        }
      }
    });
  }, {
    rootMargin: '200px', // OVC: pdf - увеличиваем запас для предзагрузки страниц
    threshold: 0.1, // Загружаем когда видно хотя бы 10% страницы
  });
  
  function loadPage(img, priority = false) {
    const pageNum = parseInt(img.dataset.pageNum || '1', 10);
    if (pageNum < 1 || pageNum > pages) {
      console.warn('PDF viewer: invalid page number', { pageNum, pages });
      return;
    }
    
    // Не загружаем, если уже загружается или загружена
    if (img.dataset.loading === 'true') {
      console.log('PDF viewer: page already loading', { 
        pageNum, 
        loading: img.dataset.loading
      });
      return;
    }
    
    // OVC: pdf - проверяем, есть ли сохраненный src в dataset (после частичной перерисовки)
    if (img.dataset.savedSrc && img.dataset.savedSrc !== '') {
      console.log('PDF viewer: restoring saved src from dataset', { 
        pageNum, 
        savedSrc: img.dataset.savedSrc.substring(0, 50)
      });
      img.src = img.dataset.savedSrc;
      // Восстанавливаем состояние загруженного изображения
      img.dataset.loaded = 'true';
      img.dataset.loading = 'false';
      img.classList.add('pdf-page-img-loaded');
      // Скрываем placeholder
      const placeholder = img.parentElement?.querySelector('.pdf-page-placeholder');
      if (placeholder) {
        placeholder.setAttribute('hidden', '');
        placeholder.style.display = 'none';
      }
      return;
    }
    
    // OVC: pdf - проверяем глобальный кэш (после полной перерисовки блока)
    const cacheKey = `${fileId}_page_${pageNum}`;
    const cachedState = imageStateCache.get(cacheKey);
    if (cachedState && cachedState.loaded && cachedState.src) {
      console.log('PDF viewer: restoring from cache', { 
        pageNum, 
        cachedSrc: cachedState.src.substring(0, 50)
      });
      img.src = cachedState.src;
      img.dataset.savedSrc = cachedState.src; // Сохраняем также в dataset
      img.dataset.loaded = 'true';
      img.dataset.loading = 'false';
      img.classList.add('pdf-page-img-loaded');
      // Скрываем placeholder
      const placeholder = img.parentElement?.querySelector('.pdf-page-placeholder');
      if (placeholder) {
        placeholder.setAttribute('hidden', '');
        placeholder.style.display = 'none';
      }
      return;
    }
    
    if (img.src && img.src !== '') {
      console.log('PDF viewer: page already has src', { 
        pageNum, 
        hasSrc: !!img.src && img.src !== '',
        src: img.src.substring(0, 50)
      });
      return;
    }
    
    if (img.dataset.loaded === 'true') {
      console.log('PDF viewer: page already loaded', { 
        pageNum, 
        loaded: img.dataset.loaded
      });
      return;
    }
    
    img.dataset.loading = 'true';
    const url = `/files/${fileId}/page/${pageNum}?scale=${currentZoom}`;
    
    // OVC: pdf - логируем время начала загрузки для анализа производительности
    const startTime = performance.now();
    console.log('PDF viewer: loading page', { pageNum, url, fileId, priority });
    
    // OVC: pdf - используем прямое присвоение src к URL сервера
    // Это самый надежный способ для загрузки изображений
    // Браузер сам обработает кэширование и события загрузки
    
    // OVC: pdf - флаг для предотвращения множественных вызовов
    let loadHandled = false;
    let errorHandled = false;
    
    // OVC: pdf - создаем функцию для обработки загрузки и отображения
    const handleImageLoad = () => {
      // Защита от множественных вызовов
      if (loadHandled) {
        console.log('PDF viewer: handleImageLoad already called, skipping', { pageNum });
        return;
      }
      loadHandled = true;
      
      console.log('PDF viewer: handleImageLoad called', { 
        pageNum, 
        complete: img.complete, 
        naturalWidth: img.naturalWidth, 
        naturalHeight: img.naturalHeight,
        src: img.src?.substring(0, 50)
      });
      
      // OVC: pdf - проверяем, что изображение действительно загрузилось
      if (!img.complete || img.naturalWidth === 0 || img.naturalHeight === 0) {
        console.warn('PDF viewer: image marked as loaded but dimensions are zero', { 
          pageNum,
          complete: img.complete,
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight
        });
        loadHandled = false; // Разрешаем повторную попытку
        return;
      }
      
      // OVC: pdf - отмечаем изображение как загруженное
      img.dataset.loaded = 'true';
      img.dataset.loading = 'false';
      
      const loadTime = ((performance.now() - startTime) / 1000).toFixed(2);
      console.log('PDF viewer: page loaded successfully', { 
        pageNum, 
        loadTime: `${loadTime}s`,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight
      });
      
      // OVC: pdf - скрываем placeholder
      const placeholder = img.parentElement?.querySelector('.pdf-page-placeholder');
      if (placeholder) {
        placeholder.setAttribute('hidden', '');
        placeholder.style.display = 'none';
      }
      
          // OVC: pdf - убираем все inline стили, которые могут скрывать изображение
          img.style.removeProperty('display');
          img.style.removeProperty('opacity');
          img.style.removeProperty('visibility');
          
          // Принудительно устанавливаем видимость через класс
          img.classList.add('pdf-page-img-loaded');
          
          // OVC: pdf - сохраняем src в dataset для восстановления после перерисовки
          // Это поможет сохранить изображение, даже если блок будет перерисован
          img.dataset.savedSrc = img.src;
          
          // OVC: pdf - также сохраняем в глобальном кэше для восстановления после полной перерисовки
          const cacheKey = `${fileId}_page_${pageNum}`;
          imageStateCache.set(cacheKey, {
            src: img.src,
            loaded: true,
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight
          });
    };
    
    const handleImageError = (e) => {
      // Защита от множественных вызовов
      if (errorHandled) {
        console.log('PDF viewer: handleImageError already called, skipping', { pageNum });
        return;
      }
      errorHandled = true;
      
      console.error('PDF viewer: img.onerror fired', { 
        pageNum, 
        error: e,
        src: img.src?.substring(0, 50),
        complete: img.complete,
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight
      });
      
      img.dataset.loading = 'false';
      showPageError(img, pageNum, 'Ошибка загрузки изображения.');
    };
    
    // OVC: pdf - устанавливаем ТОЛЬКО addEventListener (не дублируем с onload/onerror)
    // Используем { once: true } чтобы избежать множественных вызовов
    img.addEventListener('load', handleImageLoad, { once: true });
    img.addEventListener('error', handleImageError, { once: true });
    
    // OVC: pdf - устанавливаем URL сервера напрямую как src
    console.log('PDF viewer: setting img.src to server URL', { pageNum, url });
    img.src = url;
    
    // OVC: pdf - проверяем загрузку через requestAnimationFrame
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!loadHandled && !errorHandled && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
          console.log('PDF viewer: image loaded instantly (RAF fallback)', { 
            pageNum, 
            complete: img.complete, 
            naturalWidth: img.naturalWidth,
            naturalHeight: img.naturalHeight
          });
          handleImageLoad();
        }
      });
    });
    
    // OVC: pdf - проверка через таймаут
    setTimeout(() => {
      if (!loadHandled && !errorHandled && img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
        console.log('PDF viewer: image loaded (timeout fallback)', { 
          pageNum, 
          complete: img.complete, 
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight
        });
        handleImageLoad();
      }
    }, 300);
    
    // OVC: pdf - таймаут для ошибки загрузки
    setTimeout(() => {
      if (!loadHandled && !errorHandled && img.dataset.loading === 'true') {
        console.error('PDF viewer: image load timeout after 10s', { 
          pageNum, 
          complete: img.complete,
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight,
          hasSrc: !!img.src,
          src: img.src?.substring(0, 50)
        });
        handleImageError(new Error('Image load timeout'));
      }
    }, 10000);
  }
  
  function showPageError(img, pageNum, errorMessage) {
    const placeholder = img.parentElement.querySelector('.pdf-page-placeholder');
    if (placeholder) {
      placeholder.style.background = 'rgba(239, 68, 68, 0.1)';
      placeholder.style.borderColor = 'rgba(239, 68, 68, 0.5)';
      placeholder.style.color = 'rgba(239, 68, 68, 0.8)';
      placeholder.textContent = `❌ Ошибка загрузки страницы ${pageNum}\n${errorMessage}`;
      placeholder.style.display = 'flex';
    } else {
      // Если placeholder нет, показываем ошибку на самом изображении
      img.style.opacity = '1';
      img.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
      img.style.minHeight = '400px';
      img.style.display = 'flex';
      img.style.alignItems = 'center';
      img.style.justifyContent = 'center';
      img.style.color = 'white';
      img.style.fontSize = '18px';
      img.style.textAlign = 'center';
      img.style.padding = '20px';
      img.alt = `Ошибка загрузки страницы ${pageNum}: ${errorMessage}`;
    }
  }
  
  function ensurePagesMounted() {
    if (pagesContainer.children.length > 0) {
      console.log('PDF viewer: pages already mounted', { count: pagesContainer.children.length });
      // Убеждаемся, что все существующие страницы наблюдаются
      pagesContainer.querySelectorAll('.pdf-page').forEach(page => {
        pageObserver.observe(page);
        
        // OVC: pdf - проверяем и восстанавливаем изображения из кэша для существующих страниц
        const img = page.querySelector('img');
        if (img && !img.src && !img.dataset.loaded) {
          const pageNum = parseInt(img.dataset.pageNum || page.dataset.n || '1', 10);
          const cacheKey = `${fileId}_page_${pageNum}`;
          const cachedState = imageStateCache.get(cacheKey);
          if (cachedState && cachedState.loaded && cachedState.src) {
            console.log('PDF viewer: restoring existing page from cache', { pageNum, cachedSrc: cachedState.src.substring(0, 50) });
            img.src = cachedState.src;
            img.dataset.savedSrc = cachedState.src;
            img.dataset.loaded = 'true';
            img.dataset.loading = 'false';
            img.classList.add('pdf-page-img-loaded');
            const placeholder = page.querySelector('.pdf-page-placeholder');
            if (placeholder) {
              placeholder.setAttribute('hidden', '');
              placeholder.style.display = 'none';
            }
          }
        }
      });
      return; // Уже смонтированы
    }
    
    console.log('PDF viewer: mounting pages', { pages, fileId, containerVisible: pagesContainer.offsetParent !== null });
    
    if (pages <= 0) {
      console.error('PDF viewer: invalid pages count', pages);
      return;
    }
    
    for (let i = 1; i <= pages; i++) {
      const figure = document.createElement('figure');
      figure.className = 'pdf-page';
      figure.dataset.n = String(i);
      
      // OVC: pdf - добавляем placeholder для визуальной обратной связи
      const placeholder = document.createElement('div');
      placeholder.className = 'pdf-page-placeholder';
      placeholder.style.cssText = 'min-height: 400px; background: rgba(139, 92, 246, 0.1); border: 2px dashed rgba(139, 92, 246, 0.3); display: flex; align-items: center; justify-content: center; color: rgba(255, 255, 255, 0.5);';
      placeholder.textContent = `Загрузка страницы ${i}...`;
      figure.appendChild(placeholder);
      
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.alt = `Страница ${i}`;
      img.dataset.pageNum = String(i);
      img.dataset.loading = 'false'; // OVC: pdf - начинаем с false, будет true когда начнем загрузку
      img.style.width = '100%';
      img.style.height = 'auto';
      // OVC: pdf - НЕ устанавливаем display: none здесь, CSS сам скроет через селектор [data-loading="true"]
      // Но нужно скрыть через CSS, чтобы placeholder был виден
      
      // OVC: pdf - предотвращаем всплытие событий клика на изображениях, чтобы не сбрасывать состояние
      img.addEventListener('click', (e) => {
        e.stopPropagation(); // Предотвращаем всплытие, чтобы клик не обрабатывался родительскими элементами
      }, { passive: true });
      
      img.addEventListener('mousedown', (e) => {
        e.stopPropagation(); // Предотвращаем всплытие mousedown
      }, { passive: true });
      
      // OVC: pdf - проверяем кэш перед добавлением элемента, чтобы сразу восстановить изображение
      const cacheKey = `${fileId}_page_${i}`;
      const cachedState = imageStateCache.get(cacheKey);
      if (cachedState && cachedState.loaded && cachedState.src) {
        console.log('PDF viewer: restoring new page from cache immediately', { pageNum: i, cachedSrc: cachedState.src.substring(0, 50) });
        img.src = cachedState.src;
        img.dataset.savedSrc = cachedState.src;
        img.dataset.loaded = 'true';
        img.dataset.loading = 'false';
        img.classList.add('pdf-page-img-loaded');
        placeholder.setAttribute('hidden', '');
        placeholder.style.display = 'none';
      }
      
      // OVC: pdf - обработчики событий не нужны здесь, так как загрузка идет через loadPage()
      
      figure.appendChild(img);
      pagesContainer.appendChild(figure);
      
      // OVC: pdf - подключаем каждую страницу к observer для lazy-loading
      pageObserver.observe(figure);
      
      console.log('PDF viewer: page element created', { pageNum: i, container: pagesContainer, figure, restoredFromCache: !!cachedState });
    }
    
    console.log('PDF viewer: pages mounted and observed', { 
      count: pagesContainer.children.length,
      containerStyle: window.getComputedStyle(pagesContainer).display,
      containerHidden: pagesContainer.hidden,
      containerVisible: pagesContainer.offsetParent !== null
    });
  }
  
  function updateZoom(newZoom) {
    newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, newZoom));
    if (newZoom === currentZoom) return;
    
    currentZoom = newZoom;
    
    // Перезагружаем все загруженные страницы с новым масштабом
    const loadedImgs = pagesContainer.querySelectorAll('img[src]');
    loadedImgs.forEach(img => {
      const pageNum = parseInt(img.dataset.pageNum || '1', 10);
      img.src = `/files/${fileId}/page/${pageNum}?scale=${currentZoom}`;
    });
  }
  
  function getCurrentPage() {
    // Находим страницу, которая ближе всего к центру viewport
    const pages = Array.from(pagesContainer.querySelectorAll('.pdf-page'));
    if (pages.length === 0) return 1;
    
    const containerRect = pagesContainer.getBoundingClientRect();
    const centerY = containerRect.top + containerRect.height / 2;
    
    let closestPage = pages[0];
    let minDistance = Infinity;
    
    pages.forEach(page => {
      const rect = page.getBoundingClientRect();
      const pageCenterY = rect.top + rect.height / 2;
      const distance = Math.abs(pageCenterY - centerY);
      if (distance < minDistance) {
        minDistance = distance;
        closestPage = page;
      }
    });
    
    return parseInt(closestPage.dataset.n || '1', 10);
  }
  
  function scrollToPage(pageNum) {
    const page = pagesContainer.querySelector(`.pdf-page[data-n="${pageNum}"]`);
    if (page) {
      page.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  
  function toggleView() {
    const currentView = block.dataset.view || 'cover';
    const newView = currentView === 'cover' ? 'inline' : 'cover';
    view = newView;  // OVC: pdf - обновляем локальную переменную
    block.dataset.view = newView;
    
    console.log('PDF viewer: toggling view', { 
      currentView, 
      newView, 
      blockId: block.dataset.blockId,
      coverHidden: cover.hidden,
      pagesContainerHidden: pagesContainer.hidden,
      pagesContainerChildren: pagesContainer.children.length
    });
    
    if (newView === 'inline') {
      console.log('PDF viewer: switching to inline view', {
        fileId,
        pages,
        coverExists: !!cover,
        pagesContainerExists: !!pagesContainer,
        containerBefore: {
          display: window.getComputedStyle(pagesContainer).display,
          hidden: pagesContainer.hidden,
          visible: pagesContainer.offsetParent !== null
        }
      });
      
      // Скрываем обложку (используем и hidden и display для надежности)
      if (cover) {
        cover.setAttribute('hidden', '');
        cover.style.display = 'none';
      }
      
      // Показываем контейнер страниц - ВАЖНО: убираем hidden и устанавливаем display
      pagesContainer.removeAttribute('hidden');
      pagesContainer.style.display = 'flex';
      pagesContainer.style.visibility = 'visible';
      pagesContainer.style.opacity = '1';
      
      console.log('PDF viewer: container shown', {
        display: window.getComputedStyle(pagesContainer).display,
        hidden: pagesContainer.hidden,
        visible: pagesContainer.offsetParent !== null,
        height: pagesContainer.offsetHeight,
        width: pagesContainer.offsetWidth
      });
      
      // Монтируем страницы
      ensurePagesMounted();
      console.log('PDF viewer: pages mounted', { 
        pagesCount: pagesContainer.children.length,
        fileId,
        pages,
        containerDisplay: window.getComputedStyle(pagesContainer).display,
        containerHidden: pagesContainer.hidden,
        containerVisible: pagesContainer.offsetParent !== null,
        containerHeight: pagesContainer.offsetHeight
      });
      
      // Включаем кнопки toolbar
      toolbar.querySelectorAll('.doc-btn[data-action]').forEach(btn => {
        if (btn.dataset.action !== 'toggle-view') {
          btn.disabled = false;
        }
      });
      
      // Обновляем текст кнопки
      const toggleBtn = toolbar.querySelector('[data-action="toggle-view"]');
      if (toggleBtn) toggleBtn.textContent = 'Свернуть';
      
      // Загружаем первые страницы сразу после монтирования
      // Остальные загрузятся автоматически через IntersectionObserver
      requestAnimationFrame(() => {
        const pageElements = pagesContainer.querySelectorAll('.pdf-page');
        console.log('PDF viewer: preparing to load pages', { 
          pageElementsCount: pageElements.length,
          totalPages: pages,
          containerVisible: pagesContainer.offsetParent !== null
        });
        
        if (pageElements.length === 0) {
          console.error('PDF viewer: no pages found after mount!');
          return;
        }
        
        // OVC: pdf - загружаем страницы с оптимизацией производительности
        console.log('PDF viewer: starting to load pages', { 
          totalPages: pages,
          pageElementsCount: pageElements.length,
          containerVisible: pagesContainer.offsetParent !== null
        });
        
        if (pageElements.length === 0) {
          console.error('PDF viewer: no page elements found!');
          return;
        }
        
        const totalLoadStartTime = performance.now();
        let loadedCount = 0;
        const totalPages = pageElements.length;
        
        // OVC: pdf - загружаем все страницы с небольшой задержкой
        // Для файлов <= 5 страниц загружаем все сразу, для больших - первые 3 сразу, остальные lazy
        pageElements.forEach((page, index) => {
          const img = page.querySelector('img');
          if (!img) {
            console.error('PDF viewer: img element not found in page', index);
            return;
          }
          
          const pageNum = parseInt(img.dataset.pageNum || String(index + 1), 10);
          
          // OVC: pdf - проверяем состояние перед планированием загрузки
          const alreadyLoading = img.dataset.loading === 'true';
          const alreadyLoaded = img.dataset.loaded === 'true';
          const hasSrc = img.src && img.src !== '';
          
          if (alreadyLoading || alreadyLoaded || hasSrc) {
            console.log('PDF viewer: page already processed', { 
              pageNum, 
              loading: alreadyLoading, 
              loaded: alreadyLoaded, 
              hasSrc 
            });
            return;
          }
          
          // OVC: pdf - для небольших файлов загружаем все сразу с минимальной задержкой
          // Для больших - первые 3 сразу, остальные с задержкой
          const delay = totalPages <= 5 
            ? index * 10  // 10ms между запросами для небольших файлов
            : (pageNum <= 3 ? 0 : (pageNum - 3) * 50); // 50ms между запросами для больших
          
          console.log('PDF viewer: scheduling page load', { 
            pageNum, 
            index, 
            totalPages,
            delay,
            currentSrc: img.src || '(empty)',
            currentLoading: img.dataset.loading || '(not set)',
            currentLoaded: img.dataset.loaded || '(not set)'
          });
          
          // OVC: pdf - используем setTimeout для загрузки с задержкой
          setTimeout(() => {
            // OVC: pdf - проверяем актуальное состояние на момент выполнения
            const shouldLoad = !img.src && 
                              img.dataset.loading !== 'true' && 
                              img.dataset.loaded !== 'true' &&
                              img.parentElement !== null; // Убеждаемся, что элемент еще в DOM
            
            console.log('PDF viewer: setTimeout callback executed', { 
              pageNum, 
              delay,
              hasSrc: !!img.src, 
              src: img.src || '(empty)',
              loading: img.dataset.loading || '(not set)', 
              loaded: img.dataset.loaded || '(not set)',
              shouldLoad,
              imgStillExists: !!img && img.parentElement !== null
            });
            
            if (shouldLoad) {
              console.log('PDF viewer: calling loadPage', pageNum);
              try {
                loadPage(img, pageNum <= 3);
              } catch (error) {
                console.error('PDF viewer: error in loadPage', { pageNum, error });
              }
            } else {
              console.warn('PDF viewer: skipping loadPage', { 
                pageNum, 
                reason: !img.src ? 'has src' : 
                        img.dataset.loading === 'true' ? 'already loading' : 
                        img.dataset.loaded === 'true' ? 'already loaded' : 
                        img.parentElement === null ? 'removed from DOM' : 'unknown'
              });
            }
          }, delay);
        });
        
        // Дополнительно: проверяем видимые страницы и загружаем их сразу
        // Это нужно, если контейнер уже виден после переключения
        setTimeout(() => {
          const visiblePages = Array.from(pageElements).filter(page => {
            const rect = page.getBoundingClientRect();
            const containerRect = pagesContainer.getBoundingClientRect();
            return rect.top < containerRect.bottom && rect.bottom > containerRect.top;
          });
          
          visiblePages.forEach(page => {
            const img = page.querySelector('img');
            if (img && !img.src && !img.dataset.loading) {
              const pageNum = parseInt(img.dataset.pageNum || '1', 10);
              console.log('PDF viewer: loading visible page immediately', pageNum);
              loadPage(img);
            }
          });
        }, 50);
      });
    } else {
      console.log('PDF viewer: switching to cover view');
      
      // Показываем обложку
      cover.removeAttribute('hidden');
      cover.style.display = 'block';
      
      // Скрываем контейнер страниц
      pagesContainer.setAttribute('hidden', '');
      pagesContainer.style.display = 'none';
      
      // Отключаем кнопки toolbar (кроме toggle-view)
      toolbar.querySelectorAll('.doc-btn[data-action]').forEach(btn => {
        if (btn.dataset.action !== 'toggle-view') {
          btn.disabled = true;
        }
      });
      
      // Обновляем текст кнопки
      const toggleBtn = toolbar.querySelector('[data-action="toggle-view"]');
      if (toggleBtn) toggleBtn.textContent = 'Просмотр';
    }
    
    // Сохраняем изменения в блоке
    if (onBlockUpdate) {
      const blockId = block.dataset.blockId;
      if (blockId) {
        console.log('PDF viewer: updating block', blockId, { view: newView });
        onBlockUpdate(blockId, { view: newView });
      } else {
        console.warn('PDF viewer: blockId not found for update');
      }
    }
  }
  
  function handleZoomIn() {
    updateZoom(currentZoom + ZOOM_STEP);
  }
  
  function handleZoomOut() {
    updateZoom(currentZoom - ZOOM_STEP);
  }
  
  function handlePrev() {
    const currentPage = getCurrentPage();
    if (currentPage > 1) {
      scrollToPage(currentPage - 1);
    }
  }
  
  function handleNext() {
    const currentPage = getCurrentPage();
    if (currentPage < pages) {
      scrollToPage(currentPage + 1);
    }
  }
  
  function handleToTop() {
    pagesContainer.scrollTo({ top: 0, behavior: 'smooth' });
  }
  
  // Обработчики событий для toolbar (делегирование событий)
  // Используем один обработчик на toolbar для всех кнопок
  toolbar.addEventListener('click', (e) => {
    e.stopPropagation(); // Предотвращаем всплытие
    
    // Ищем кнопку с data-action (может быть клик по тексту внутри кнопки)
    const button = e.target.closest('button[data-action]');
    if (!button || button.disabled) {
      return;
    }
    
    const action = button.dataset.action;
    if (!action) {
      return;
    }
    
    e.preventDefault();
    
    console.log('PDF viewer: toolbar action', { action, button: button.textContent, blockId: block.dataset.blockId });
    
    switch (action) {
      case 'toggle-view':
        toggleView();
        break;
      case 'zoom-in':
        handleZoomIn();
        break;
      case 'zoom-out':
        handleZoomOut();
        break;
      case 'prev':
        handlePrev();
        break;
      case 'next':
        handleNext();
        break;
      case 'to-top':
        handleToTop();
        break;
      default:
        console.warn('PDF viewer: unknown action', action);
    }
  });
  
  // Инициализация: если view === 'inline', монтируем страницы сразу
  console.log('PDF viewer: checking initial view', { view, blockView: block.dataset.view, coverHidden: cover.hidden, pagesContainerHidden: pagesContainer.hidden });
  
  if (view === 'inline') {
    console.log('PDF viewer: initializing in inline mode');
    
    // Показываем контейнер страниц
    if (cover) {
      cover.setAttribute('hidden', '');
      cover.style.display = 'none';
    }
    pagesContainer.removeAttribute('hidden');
    pagesContainer.style.display = 'flex';
    pagesContainer.style.visibility = 'visible';
    pagesContainer.style.opacity = '1';
    
    console.log('PDF viewer: container shown for inline mode', {
      display: window.getComputedStyle(pagesContainer).display,
      hidden: pagesContainer.hidden,
      visible: pagesContainer.offsetParent !== null
    });
    
    // Монтируем страницы
    ensurePagesMounted();
    
    // Включаем кнопки toolbar
    toolbar.querySelectorAll('.doc-btn[data-action]').forEach(btn => {
      if (btn.dataset.action !== 'toggle-view') {
        btn.disabled = false;
      }
    });
    
    // Обновляем текст кнопки
    const toggleBtn = toolbar.querySelector('[data-action="toggle-view"]');
    if (toggleBtn) toggleBtn.textContent = 'Свернуть';
    
    // Загружаем все страницы - используем тот же код, что и в toggleView
    setTimeout(() => {
      const pageElements = pagesContainer.querySelectorAll('.pdf-page');
      console.log('PDF viewer: initializing inline mode, loading pages', { 
        pageElementsCount: pageElements.length,
        totalPages: pages,
        containerVisible: pagesContainer.offsetParent !== null
      });
      
      if (pageElements.length === 0) {
        console.error('PDF viewer: no page elements found in inline init!');
        return;
      }
      
      const totalLoadStartTime = performance.now();
      let loadedCount = 0;
      const totalPages = pageElements.length;
      
      // Загружаем все страницы сразу для небольших файлов
      pageElements.forEach((page, index) => {
        const img = page.querySelector('img');
        if (!img) {
          console.error('PDF viewer: img element not found in page', index);
          return;
        }
        
        if (img.src || img.dataset.loading === 'true') {
          console.log('PDF viewer: page already loading or loaded', index);
          return;
        }
        
        const pageNum = parseInt(img.dataset.pageNum || String(index + 1), 10);
        console.log('PDF viewer: scheduling page load in init', { pageNum, index, imgExists: !!img });
        
        // Загружаем все страницы с небольшой задержкой
        const delay = pageNum <= 2 ? 0 : (pageNum - 2) * 50; // 50ms между запросами
        setTimeout(() => {
          if (!img.src && !img.dataset.loading) {
            console.log('PDF viewer: starting load for page in init', pageNum);
            loadPage(img, pageNum <= 2);
            
            // Отслеживаем загрузку
            const checkLoaded = () => {
              if (img.complete && img.naturalHeight > 0) {
                loadedCount++;
                console.log(`PDF viewer: page ${pageNum} loaded in init (${loadedCount}/${totalPages})`);
                if (loadedCount === totalPages) {
                  const totalTime = ((performance.now() - totalLoadStartTime) / 1000).toFixed(2);
                  console.log(`PDF viewer: ✅ all ${totalPages} pages loaded in init in ${totalTime}s`);
                }
              } else if (img.dataset.loading !== 'true') {
                // Если не загружается и не загружена, проверяем через 100ms
                setTimeout(checkLoaded, 100);
              }
            };
            setTimeout(checkLoaded, 200);
          }
        }, delay);
      });
    }, 100); // Небольшая задержка для гарантии, что DOM готов
  } else {
    console.log('PDF viewer: initializing in cover mode', { view, blockView: block.dataset.view });
  }
}

