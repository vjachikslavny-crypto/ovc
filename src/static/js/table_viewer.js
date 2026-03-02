const stateMap = new WeakMap();
const WINDOW_LIMIT = 500;
const SUMMARY_RETRY_MS = 2000;

export function initTableViewers(container, onBlockUpdate) {
  const blocks = container.querySelectorAll('.table-block--excel');
  if (!blocks.length) return;

  blocks.forEach((block) => {
    if (block.dataset.tableViewerReady === 'true') return;
    block.dataset.tableViewerReady = 'true';
    setupTableBlock(block, onBlockUpdate);
  });
}

function setupTableBlock(block, onBlockUpdate) {
  const summaryUrl = block.dataset.summaryUrl;
  if (!summaryUrl) return;

  const state = {
    summary: null,
    sheet: block.dataset.activeSheet || null,
    offset: 0,
    limit: WINDOW_LIMIT,
    total: 0,
    columns: [],
    rows: [],
    filter: '',
    wrap: false,
    processing: false,
  };
  stateMap.set(block, state);

  const toggleBtn = block.querySelector('[data-action="toggle-view"]');
  const coverEl = block.querySelector('[data-role="cover"]');
  const inlineEl = block.querySelector('[data-role="inline"]');
  const infoEl = block.querySelector('[data-role="cover-info"]');
  const previewEl = block.querySelector('[data-role="preview-table"]');
  const sheetSelect = block.querySelector('[data-role="sheet-select"]');
  const prevSheetBtn = block.querySelector('[data-action="prev-sheet"]');
  const nextSheetBtn = block.querySelector('[data-action="next-sheet"]');
  
  console.log('Table viewer setup:', {
    prevSheetBtn: !!prevSheetBtn,
    nextSheetBtn: !!nextSheetBtn,
    sheetSelect: !!sheetSelect,
    blockId: block.dataset.blockId,
    blockHTML: block.outerHTML.substring(0, 200)
  });
  
  // Проверяем, что кнопки действительно в DOM
  const allPrevButtons = block.querySelectorAll('[data-action="prev-sheet"]');
  const allNextButtons = block.querySelectorAll('[data-action="next-sheet"]');
  console.log('All prev-sheet buttons found:', allPrevButtons.length);
  console.log('All next-sheet buttons found:', allNextButtons.length);
  
  if (!prevSheetBtn || !nextSheetBtn) {
    console.error('Buttons not found during setup!', {
      prevSheetBtn: !!prevSheetBtn,
      nextSheetBtn: !!nextSheetBtn,
      allPrevButtons: allPrevButtons.length,
      allNextButtons: allNextButtons.length
    });
  }
  
  // OVC: excel - поиск и кнопка переноса убраны
  const downloadSheet = block.querySelector('[data-role="download-sheet"]');
  const rowsEl = block.querySelector('[data-role="rows"]');
  const colsEl = block.querySelector('[data-role="columns"]');
  const emptyEl = block.querySelector('[data-role="empty-state"]');
  const dataTable = block.querySelector('.data-grid');
  // OVC: excel - footer с пагинацией убран

  const view = block.dataset.view || 'cover';
  updateView(block, view, coverEl, inlineEl, toggleBtn);
  
  // OVC: table - скрываем пустое состояние по умолчанию
  if (emptyEl) {
    emptyEl.hidden = true;
    emptyEl.style.display = 'none';
  }

  // OVC: excel - диаграммы отключены, фокус на предпросмотре таблиц
  
  toggleBtn?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    const currentView = block.dataset.view;
    const nextView = currentView === 'inline' ? 'cover' : 'inline';
    
    console.log('[TableViewer] Toggle clicked:', {
      currentView,
      nextView,
      coverHidden: coverEl?.hidden,
      inlineHidden: inlineEl?.hidden
    });
    
    updateView(block, nextView, coverEl, inlineEl, toggleBtn);
    
    if (typeof onBlockUpdate === 'function') {
      onBlockUpdate(block.dataset.blockId, { view: nextView });
    }
    
    if (nextView === 'inline') {
      ensureSummary(summaryUrl, infoEl, previewEl, sheetSelect, block, state, onBlockUpdate).then(() => {
        if (state.sheet) {
          updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn);
          loadSheetWindow(block, state, summaryUrl, rowsEl, colsEl, emptyEl, downloadSheet);
        }
      });
    }
    
    console.log('[TableViewer] After toggle:', {
      view: block.dataset.view,
      coverHidden: coverEl?.hidden,
      inlineHidden: inlineEl?.hidden,
      toggleBtnText: toggleBtn?.textContent
    });
  });

  sheetSelect?.addEventListener('change', () => {
    state.sheet = sheetSelect.value;
    state.offset = 0;
    block.dataset.activeSheet = state.sheet || '';
    if (typeof onBlockUpdate === 'function') {
      onBlockUpdate(block.dataset.blockId, { activeSheet: state.sheet });
    }
    updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn);
    loadSheetWindow(block, state, summaryUrl, rowsEl, colsEl, emptyEl, downloadSheet);
  });

  // Обработчики для кнопок переключения листов
  if (prevSheetBtn) {
    prevSheetBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      console.log('prevSheetBtn clicked', { 
        summary: !!state.summary, 
        sheet: state.sheet,
        disabled: prevSheetBtn.disabled,
        summarySheets: state.summary?.sheets?.length || 0
      });
      
      if (prevSheetBtn.disabled) {
        console.warn('prevSheetBtn is disabled, ignoring click');
        return;
      }
      
      if (!state.summary || !state.sheet) {
        console.warn('Cannot switch sheet: missing summary or sheet', { summary: !!state.summary, sheet: state.sheet });
        return;
      }
      const sheets = state.summary.sheets || [];
      const currentIndex = sheets.findIndex(s => s.name === state.sheet);
      console.log('Current sheet index:', currentIndex, 'Total sheets:', sheets.length);
      if (currentIndex > 0) {
        const prevSheet = sheets[currentIndex - 1];
        console.log('Switching to previous sheet:', prevSheet.name);
        state.sheet = prevSheet.name;
        state.offset = 0;
        block.dataset.activeSheet = state.sheet;
        if (sheetSelect) {
          sheetSelect.value = state.sheet;
        }
        if (typeof onBlockUpdate === 'function') {
          onBlockUpdate(block.dataset.blockId, { activeSheet: state.sheet });
        }
        updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn);
        loadSheetWindow(block, state, summaryUrl, rowsEl, colsEl, emptyEl, downloadSheet);
      } else {
        console.warn('Already at first sheet');
      }
    });
    console.log('prevSheetBtn event listener attached');
  } else {
    console.warn('prevSheetBtn not found in DOM');
  }

  if (nextSheetBtn) {
    nextSheetBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      console.log('nextSheetBtn clicked', { 
        summary: !!state.summary, 
        sheet: state.sheet,
        disabled: nextSheetBtn.disabled,
        summarySheets: state.summary?.sheets?.length || 0
      });
      
      if (nextSheetBtn.disabled) {
        console.warn('nextSheetBtn is disabled, ignoring click');
        return;
      }
      
      if (!state.summary || !state.sheet) {
        console.warn('Cannot switch sheet: missing summary or sheet', { summary: !!state.summary, sheet: state.sheet });
        return;
      }
      const sheets = state.summary.sheets || [];
      const currentIndex = sheets.findIndex(s => s.name === state.sheet);
      console.log('Current sheet index:', currentIndex, 'Total sheets:', sheets.length);
      if (currentIndex >= 0 && currentIndex < sheets.length - 1) {
        const nextSheet = sheets[currentIndex + 1];
        console.log('Switching to next sheet:', nextSheet.name);
        state.sheet = nextSheet.name;
        state.offset = 0;
        block.dataset.activeSheet = state.sheet;
        if (sheetSelect) {
          sheetSelect.value = state.sheet;
        }
        if (typeof onBlockUpdate === 'function') {
          onBlockUpdate(block.dataset.blockId, { activeSheet: state.sheet });
        }
        updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn);
        loadSheetWindow(block, state, summaryUrl, rowsEl, colsEl, emptyEl, downloadSheet);
      } else {
        console.warn('Already at last sheet');
      }
    });
    console.log('nextSheetBtn event listener attached');
  } else {
    console.warn('nextSheetBtn not found in DOM');
  }

  // OVC: excel - поиск по окну убран

  // OVC: excel - кнопка переноса и пагинация убраны

  downloadSheet?.addEventListener('click', (event) => {
    if (!state.sheet) {
      event.preventDefault();
      console.warn('downloadSheet: no sheet selected');
      return;
    }
    const csvUrl = buildSheetUrl(summaryUrl, state.sheet, 'csv');
    console.log('downloadSheet: downloading', { sheet: state.sheet, url: csvUrl });
    downloadSheet.href = csvUrl;
    // Не блокируем переход по ссылке
  });

  ensureSummary(summaryUrl, infoEl, previewEl, sheetSelect, block, state, onBlockUpdate).then(() => {
    if (block.dataset.view === 'inline' && state.sheet) {
      updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn);
      loadSheetWindow(block, state, summaryUrl, rowsEl, colsEl, emptyEl, downloadSheet);
    }
  });
}

function updateView(block, view, coverEl, inlineEl, toggleBtn) {
  console.log('[TableViewer] updateView called:', {
    view,
    coverEl: !!coverEl,
    inlineEl: !!inlineEl,
    toggleBtn: !!toggleBtn
  });
  
  block.dataset.view = view;
  
  if (coverEl) {
    coverEl.hidden = view === 'inline';
    coverEl.style.display = view === 'inline' ? 'none' : '';
  }
  
  if (inlineEl) {
    inlineEl.hidden = view !== 'inline';
    inlineEl.style.display = view === 'inline' ? '' : 'none';
  }
  
  if (toggleBtn) {
    toggleBtn.textContent = view === 'inline' ? 'Свернуть' : 'Просмотр';
  }
  
  console.log('[TableViewer] updateView result:', {
    view: block.dataset.view,
    coverHidden: coverEl?.hidden,
    coverDisplay: coverEl?.style.display,
    inlineHidden: inlineEl?.hidden,
    inlineDisplay: inlineEl?.style.display
  });
}

function updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn) {
  // Если кнопки не переданы, пытаемся найти их в DOM
  if (!prevSheetBtn) {
    prevSheetBtn = block.querySelector('[data-action="prev-sheet"]');
    console.log('updateSheetNavButtons: prevSheetBtn found in DOM:', !!prevSheetBtn);
  }
  if (!nextSheetBtn) {
    nextSheetBtn = block.querySelector('[data-action="next-sheet"]');
    console.log('updateSheetNavButtons: nextSheetBtn found in DOM:', !!nextSheetBtn);
  }
  
  if (!prevSheetBtn || !nextSheetBtn) {
    console.error('updateSheetNavButtons: buttons not found!', { prevSheetBtn: !!prevSheetBtn, nextSheetBtn: !!nextSheetBtn });
    return;
  }
  
  if (!state.summary || !state.sheet) {
    prevSheetBtn.disabled = true;
    nextSheetBtn.disabled = true;
    console.log('updateSheetNavButtons: disabled (no summary or sheet)', { 
      summary: !!state.summary, 
      sheet: state.sheet,
      summarySheets: state.summary?.sheets?.length || 0
    });
    return;
  }
  
  const sheets = state.summary.sheets || [];
  const currentIndex = sheets.findIndex(s => s.name === state.sheet);
  console.log('updateSheetNavButtons:', { 
    currentIndex, 
    totalSheets: sheets.length, 
    sheet: state.sheet,
    sheetNames: sheets.map(s => s.name)
  });
  
  prevSheetBtn.disabled = currentIndex <= 0;
  nextSheetBtn.disabled = currentIndex < 0 || currentIndex >= sheets.length - 1;
  
  console.log('updateSheetNavButtons result:', {
    prevSheetBtnDisabled: prevSheetBtn.disabled,
    nextSheetBtnDisabled: nextSheetBtn.disabled,
    canGoPrev: currentIndex > 0,
    canGoNext: currentIndex >= 0 && currentIndex < sheets.length - 1
  });
}

async function ensureSummary(summaryUrl, infoEl, previewEl, sheetSelect, block, state, onBlockUpdate, attempt = 0) {
  if (!summaryUrl || state.summary) return state.summary;
  try {
    if (infoEl) infoEl.textContent = 'Загружаем метаданные…';
    const res = await fetch(summaryUrl, { headers: { Accept: 'application/json' } });
    if (res.status === 202) {
      state.processing = true;
      if (infoEl) infoEl.textContent = 'Файл обрабатывается, попробуйте позже…';
      setTimeout(() => ensureSummary(summaryUrl, infoEl, previewEl, sheetSelect, block, state, onBlockUpdate, attempt + 1), SUMMARY_RETRY_MS * (attempt + 1));
      return null;
    }
    if (!res.ok) throw new Error(await res.text());
    const summary = await res.json();
    state.summary = summary;
    state.processing = false;
    if (!state.sheet) {
      state.sheet = summary.defaultSheet || summary.sheets?.[0]?.name || null;
      block.dataset.activeSheet = state.sheet || '';
      if (state.sheet && typeof onBlockUpdate === 'function') {
        onBlockUpdate(block.dataset.blockId, { activeSheet: state.sheet });
      }
    }
    populateSummary(summary, infoEl, previewEl, sheetSelect, state);
    
    // Обновляем состояние кнопок переключения листов после загрузки summary
    console.log('ensureSummary: summary loaded, updating buttons', {
      summarySheets: summary.sheets?.length || 0,
      currentSheet: state.sheet,
      defaultSheet: summary.defaultSheet
    });
    
    const prevSheetBtn = block.querySelector('[data-action="prev-sheet"]');
    const nextSheetBtn = block.querySelector('[data-action="next-sheet"]');
    console.log('ensureSummary: buttons found', {
      prevSheetBtn: !!prevSheetBtn,
      nextSheetBtn: !!nextSheetBtn
    });
    
    if (prevSheetBtn && nextSheetBtn) {
      updateSheetNavButtons(block, state, prevSheetBtn, nextSheetBtn);
    } else {
      console.error('ensureSummary: buttons not found in DOM!');
    }
    
    return summary;
  } catch (error) {
    console.error('excel summary error', error);
    if (infoEl) infoEl.textContent = 'Не удалось загрузить метаданные';
    return null;
  }
}

function populateSummary(summary, infoEl, previewEl, sheetSelect, state) {
  if (!summary) return;
  const sheets = summary.sheets || [];
  const sheetCount = sheets.length;
  const totalRows = sheets.reduce((acc, sheet) => acc + (sheet.rows || 0), 0);
  if (infoEl) {
    infoEl.textContent = sheetCount
      ? `${sheetCount} лист(ов) • ${totalRows.toLocaleString()} строк`
      : 'Нет данных';
  }

  if (sheetSelect) {
    sheetSelect.innerHTML = '';
    if (!sheets.length) {
      const opt = document.createElement('option');
      opt.textContent = 'Нет листов';
      opt.disabled = true;
      sheetSelect.appendChild(opt);
      sheetSelect.disabled = true;
    } else {
      sheets.forEach((sheet) => {
        const opt = document.createElement('option');
        opt.value = sheet.name;
        opt.textContent = `${sheet.name} (${sheet.rows ?? 0})`;
        if (sheet.name === state.sheet) opt.selected = true;
        sheetSelect.appendChild(opt);
      });
      sheetSelect.disabled = sheets.length === 1;
    }
  }

  if (previewEl) {
    previewEl.innerHTML = '';
    const sheet = sheets.find((item) => item.name === state.sheet) || sheets[0];
    if (!sheet || !sheet.columns?.length) {
      const placeholder = document.createElement('p');
      placeholder.className = 'table-preview-empty';
      placeholder.textContent = 'Нет предпросмотра';
      previewEl.appendChild(placeholder);
      return;
    }
    const table = document.createElement('table');
    table.className = 'table-preview-grid';
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    sheet.columns.slice(0, 6).forEach((col) => {
      const th = document.createElement('th');
      th.textContent = col || '';
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    (sheet.preview || []).forEach((row) => {
      const tr = document.createElement('tr');
      row.slice(0, 6).forEach((cell) => {
        const td = document.createElement('td');
        td.textContent = cell == null ? '' : String(cell);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    if (!sheet.preview?.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = Math.max(1, sheet.columns.length);
      td.textContent = 'Нет предпросмотра';
      tr.appendChild(td);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    previewEl.appendChild(table);
  }
}

async function loadSheetWindow(block, state, summaryUrl, rowsEl, colsEl, emptyEl, downloadSheet) {
  if (!state.sheet) {
    return;
  }
  try {
    block.dataset.loading = 'true';
    const url = buildSheetUrl(summaryUrl, state.sheet, 'json');
    const res = await fetch(`${url}?offset=${state.offset}&limit=${state.limit}`);
    if (!res.ok) throw new Error(await res.text());
    const payload = await res.json();
    state.offset = payload.offset ?? state.offset;
    state.limit = payload.limit ?? state.limit;
    state.total = payload.total ?? payload.rows?.length ?? 0;
    state.columns = payload.columns || [];
    state.rows = payload.rows || [];
    
    renderRows(state, rowsEl, colsEl, emptyEl);
    if (downloadSheet && state.sheet) {
      const csvUrl = buildSheetUrl(summaryUrl, state.sheet, 'csv');
      downloadSheet.href = csvUrl;
      downloadSheet.download = `${state.sheet}.csv`;
    }
  } catch (error) {
    console.error('excel window error', error);
  } finally {
    block.dataset.loading = 'false';
  }
}

function renderRows(state, rowsEl, colsEl, emptyEl) {
  if (!rowsEl || !colsEl) return;
  
  colsEl.innerHTML = '';
  (state.columns || []).forEach((col) => {
    const th = document.createElement('th');
    th.textContent = col || '';
    colsEl.appendChild(th);
  });

  const rows = state.rows || [];

  rowsEl.innerHTML = '';
  
  if (!rows.length) {
    if (emptyEl) {
      emptyEl.hidden = false;
      emptyEl.style.display = 'grid';
    }
  } else {
    if (emptyEl) {
      emptyEl.hidden = true;
      emptyEl.style.display = 'none';
    }
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      row.forEach((cell) => {
        const td = document.createElement('td');
        td.textContent = cell == null ? '' : String(cell);
        tr.appendChild(td);
      });
      rowsEl.appendChild(tr);
    });
  }
}

// OVC: excel - функция updatePager удалена (пагинация убрана)

function buildSheetUrl(summaryUrl, sheet, extension) {
  const base = summaryUrl.replace(/\/summary\.json$/, '');
  return `${base}/sheet/${encodeURIComponent(sheet)}.${extension}`;
}
