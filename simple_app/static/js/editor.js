import { renderNote } from './blocks_render.js';
import { initToolbar, clearSelectionSnapshot, rememberSelection } from './toolbar.js';
import { initInlineBubble } from './inline_bubble.js';
import { initPalette } from './palette.js';
import { initSmartInsert } from './smart_insert.js';
import { initInspector } from './inspector.js';
import { initHints } from './hints.js';
import { uuid } from './utils.js';
import { initUploader } from './uploader.js';
import { initPdfViewers } from './pdf_viewer.js';  // OVC: pdf - импорт PDF-виджета
import { initAudioPlayers } from './audio_player.js';
import { initAudioRecorder } from './audio_recorder.js';
import { initWordViewers } from './word_viewer.js'; // OVC: docx - просмотр DOCX/RTF
import { initSlidesViewers } from './slides_viewer.js';
import { initTableViewers } from './table_viewer.js';
import { initMarkdownViewers } from './markdown_viewer.js';

const SAVE_DEBOUNCE = 600;
const PLACEHOLDER_STRINGS = new Set(['Новый заголовок', 'Новый абзац']);

document.addEventListener('DOMContentLoaded', () => {
  const editorEl = document.querySelector('.editor');
  if (!editorEl) return;

  const canvas = document.getElementById('note-blocks');
  const floatingActions = document.querySelector('.floating-actions');
  const titleEl = document.getElementById('note-title');
  const shareBtn = document.getElementById('note-share');
  const backBtn = document.getElementById('nav-back');
  const infoBtn = document.getElementById('note-info');
  const paletteEl = document.getElementById('block-palette');
  const fabPlus = document.getElementById('fab-plus');
  const fabVoice = document.getElementById('fab-voice');
  const fabAttach = document.getElementById('fab-attach');
  const fileInput = document.getElementById('file-input');
  const dropOverlay = document.getElementById('drop-overlay');
  const uploadStatusEl = document.getElementById('upload-progress');
  const toolbarEl = document.getElementById('format-toolbar');
  const bubbleEl = document.getElementById('inline-bubble');
  const inspectorEl = document.getElementById('note-inspector');
  const hintBanner = document.getElementById('hint-banner');
  const hintText = document.getElementById('hint-text');
  const hintDismiss = document.getElementById('hint-dismiss');
  const llmToggle = document.getElementById('llm-toggle');

  const hints = initHints(hintBanner, hintText, hintDismiss);
  const inspector = initInspector(inspectorEl, {
    onSetLayoutHint: handleLayoutHintUpdate,
    fetchNoteOptions: fetchLinkableNotes,
    onCreateLink: createManualLink,
  });

  initToolbar(toolbarEl, canvas);
  initInlineBubble(bubbleEl, canvas);
  initPalette({ paletteEl, triggerEl: fabPlus, onInsert: handleInsertBlock });
  initSmartInsert(canvas, { onTransform: handleTransformBlock });
  const uploader = initUploader({
    attachBtn: fabAttach,
    fileInput,
    dropOverlay,
    statusEl: uploadStatusEl,
    ensureNote,
    onBlocksReady: handleUploadedBlocks,
    getDragState: () => dragState,
  }) || { queueFiles: async () => {} };

  initAudioRecorder({
    button: fabVoice,
    uploader,
    onReady: () => hints.push('Аудиозапись добавлена в заметку.'),
  });

  canvas.addEventListener('click', (event) => {
    const actionTarget = event.target?.closest?.('[data-action]');
    if (!actionTarget) return;
    const action = actionTarget.dataset.action;
    if (action === 'toggle-video-view') {
      const blockEl = actionTarget.closest('.note-block--video');
      toggleMediaBlockView(blockEl, 'video');
    } else if (action === 'toggle-youtube-view') {
      const blockEl = actionTarget.closest('.note-block--youtube');
      toggleMediaBlockView(blockEl, 'youtube');
    }
  });

  // Обработчик изменения названия видео
  canvas.addEventListener('input', (event) => {
    const titleInput = event.target.closest('[data-role="video-title"]');
    if (!titleInput) return;
    const blockEl = titleInput.closest('.note-block--video');
    if (!blockEl) return;
    const blockId = blockEl.dataset.blockId;
    if (!blockId) return;
    handleBlockUpdate(blockId, { title: titleInput.value });
  });

  let noteState = {
    id: editorEl.dataset.noteId || '',
    title: 'Без названия',
    styleTheme: document.body.dataset.theme || 'clean',
    blocks: [],
    layoutHints: {},
    passport: {},
    tags: [],
    linksFrom: [],
    linksTo: [],
    sources: [],
  };

  let saveTimer = null;
  let focusedBlockId = null;
  let canvasClickBound = false;
  let pendingCaretBlockId = null;
  const dragState = {
    activeId: null,
    overId: null,
    position: null,
  };
  const saveQueue = [];

  // ---- API / LOAD ----

  async function ensureNote() {
    if (noteState.id) return noteState.id;
    const res = await fetch('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Новая заметка',
        blocks: [],
        styleTheme: noteState.styleTheme,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const note = await res.json();
    noteState.id = note.id;
    window.history.replaceState({}, '', `/notes/${note.id}`);
    return note.id;
  }

  async function fetchNoteDetail(noteId) {
    const res = await fetch(`/api/notes/${noteId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function applyNote(note) {
    noteState = {
      ...noteState,
      id: note.id,
      title: note.title,
      styleTheme: note.styleTheme,
      layoutHints: note.layoutHints ?? {},
      passport: note.passport ?? {},
      blocks: cleanIncomingBlocks(note.blocks),
      tags: note.tags || [],
      linksFrom: note.linksFrom || [],
      linksTo: note.linksTo || [],
      sources: note.sources || [],
    };
    focusedBlockId = null;
    render();
  }

  async function refreshNoteState() {
    if (!noteState.id) return;
    const note = await fetchNoteDetail(noteState.id);
    applyNote(note);
  }

  async function loadNote() {
    const noteId = await ensureNote();
    const note = await fetchNoteDetail(noteId);
    applyNote(note);
    hints.push('Нажмите ＋, чтобы добавить новый блок.');
  }

  // ---- RENDER ----

  function render() {
    // OVC: title - не перерисовываем, если редактируется название заметки
    if (isEditingTitle) {
      return;
    }
    
    // Сохраняем информацию о текущем фокусе и выделении перед перерисовкой
    const activeElement = document.activeElement;
    let savedFocus = null;
    let savedSelection = null;
    let savedTableCellFocus = null;
    
    // OVC: title - не сохраняем фокус, если активный элемент - это titleEl
    if (activeElement === titleEl) {
      // Не сохраняем фокус для titleEl, чтобы не вызывать проблемы
      return;
    }
    
    if (activeElement && canvas.contains(activeElement)) {
      // Проверяем, является ли активный элемент ячейкой таблицы
      if (activeElement.tagName === 'TD' || activeElement.tagName === 'TH') {
        const tableEl = activeElement.closest('table[data-block-id]');
        if (tableEl) {
          const currentRow = activeElement.parentElement;
          const currentRowIndex = Array.from(currentRow.parentElement.children).indexOf(currentRow);
          const currentCellIndex = Array.from(currentRow.children).indexOf(activeElement);
          const selection = window.getSelection();
          
          // Сохраняем позицию курсора в ячейке
          let cursorOffset = null;
          if (selection && selection.rangeCount > 0) {
            try {
              const range = selection.getRangeAt(0);
              const textBeforeCursor = range.toString().length === 0 
                ? getTextBeforeCursor(activeElement, range)
                : null;
              if (textBeforeCursor !== null) {
                cursorOffset = textBeforeCursor.length;
              }
            } catch (e) {
              // Игнорируем ошибки
            }
          }
          
          savedTableCellFocus = {
            blockId: tableEl.dataset.blockId,
            rowIndex: currentRowIndex,
            cellIndex: currentCellIndex,
            cursorOffset: cursorOffset,
          };
        }
      } else {
        // Обычная логика для других блоков
        const focusedBlockEl = activeElement.closest('[data-block-id]');
        if (focusedBlockEl) {
          // OVC: files - не сохраняем фокус для файловых блоков, чтобы не вызывать прокрутку при восстановлении
          if (focusedBlockEl.closest('.audio-block, .doc-block--pdf, .doc-block--word, .slides-block, .table-block, .note-block--image')) {
            // Не сохраняем фокус для PDF блоков
          } else {
            const editable = getEditableElement(focusedBlockEl) || focusedBlockEl;
            if (editable === activeElement || editable.contains(activeElement)) {
              const selection = window.getSelection();
              
              // Проверяем, есть ли выделение текста
              const hasSelection = selection && selection.rangeCount > 0 && !selection.isCollapsed;
              if (hasSelection) {
                try {
                  const range = selection.getRangeAt(0);
                  // Сохраняем выделение через смещения от начала текста
                  const startRange = document.createRange();
                  startRange.selectNodeContents(editable);
                  startRange.setEnd(range.startContainer, range.startOffset);
                  const startOffset = startRange.toString().length;
                  
                  const endRange = document.createRange();
                  endRange.selectNodeContents(editable);
                  endRange.setEnd(range.endContainer, range.endOffset);
                  const endOffset = endRange.toString().length;
                  
                  savedSelection = {
                    startOffset: startOffset,
                    endOffset: endOffset,
                    selectedText: range.toString(),
                  };
                } catch (e) {
                  // Игнорируем ошибки
                }
              }
              
              // Сохраняем позицию курсора, если нет выделения
              if (!savedSelection && selection && selection.rangeCount > 0) {
                try {
                  const range = selection.getRangeAt(0);
                  const textBeforeCursor = range.toString().length === 0 
                    ? getTextBeforeCursor(editable, range)
                    : null;
                  if (textBeforeCursor !== null) {
                    savedFocus = {
                      blockId: focusedBlockEl.dataset.blockId,
                      cursorOffset: textBeforeCursor.length,
                    };
                  }
                } catch (e) {
                  // Игнорируем ошибки
                }
              }
              
              // Если есть выделение, тоже сохраняем blockId
              if (savedSelection) {
                savedFocus = {
                  blockId: focusedBlockEl.dataset.blockId,
                  selection: savedSelection,
                };
              }
            }
          }
        }
      }
    }

    titleEl.textContent = noteState.title || 'Без названия';
    
    renderNote(canvas, noteState, document.body.dataset.theme || 'clean');
    clearSelectionSnapshot();
    
    hydrateBlocks();
    
    // OVC: pdf - инициализация PDF-виджетов после рендеринга
    // Сбрасываем флаг инициализации для всех PDF-блоков перед повторной инициализацией
    canvas.querySelectorAll('.doc-block--pdf').forEach(block => {
      block.dataset.pdfViewerInitialized = 'false';
    });
    initPdfViewers(canvas, handleBlockUpdate);
    // OVC: audio - сохраняем состояние воспроизведения перед рендером
    canvas.querySelectorAll('.audio-block').forEach(block => {
      const audioEl = block.querySelector('audio');
      if (audioEl) {
        // Сохраняем текущее состояние
        audioEl.dataset.savedTime = String(audioEl.currentTime);
        audioEl.dataset.wasPlaying = String(!audioEl.paused);
        audioEl.dataset.savedSrc = audioEl.src;
      }
    });
    // OVC: audio - сбрасываем флаг инициализации только для новых блоков
    // Блоки, которые уже были инициализированы, не будут переинициализированы
    initAudioPlayers(canvas, handleBlockUpdate);
    canvas.querySelectorAll('.doc-block--word').forEach(block => {
      block.dataset.wordViewerInitialized = 'false';
    });
    initWordViewers(canvas, handleBlockUpdate);
    canvas.querySelectorAll('.slides-block').forEach(block => {
      block.dataset.slidesReady = 'false';
    });
    initSlidesViewers(canvas, handleBlockUpdate);
    initTableViewers(canvas, handleBlockUpdate);
    initMarkdownViewers(canvas);
    // Повторная обработка ячеек таблиц после перерисовки
    // ВАЖНО: hydrateTableCells сама проверит, какие ячейки нужно обработать
    // Не сбрасываем флаг tableHydrated, чтобы не терять фокус
    canvas.querySelectorAll('[data-block-type="table"], table[data-block-id]').forEach((tableEl) => {
      if (tableEl.tagName === 'TABLE') {
        hydrateTableCells(tableEl);
      }
    });
    updateFloatingActionsOffset();
    inspector.update(noteState);

    if (llmToggle) {
      llmToggle.checked = Boolean(noteState.layoutHints?.autoLLM);
    }

    // Восстанавливаем фокус ячейки таблицы после перерисовки
    if (savedTableCellFocus) {
      const targetTableEl = canvas.querySelector(
        `table[data-block-id="${savedTableCellFocus.blockId}"]`,
      );
      if (targetTableEl) {
        const rows = Array.from(targetTableEl.querySelectorAll('tr'));
        if (rows[savedTableCellFocus.rowIndex]) {
          const targetRow = rows[savedTableCellFocus.rowIndex];
          const cells = Array.from(targetRow.children);
          if (cells[savedTableCellFocus.cellIndex]) {
            const targetCell = cells[savedTableCellFocus.cellIndex];
            requestAnimationFrame(() => {
              targetCell.focus();
              // Восстанавливаем позицию курсора
              if (savedTableCellFocus.cursorOffset !== null) {
                try {
                  restoreCursorPosition(targetCell, savedTableCellFocus.cursorOffset);
                } catch (e) {
                  // Если не удалось, ставим курсор в конец
                  placeCaretAtEnd(targetCell);
                }
              } else {
                placeCaretAtEnd(targetCell);
              }
            });
          }
        }
      }
    } else if (pendingCaretBlockId) {
      // Восстанавливаем фокус для обычных блоков
      const pendingEl = canvas.querySelector(
        `[data-block-id="${pendingCaretBlockId}"]`,
      );
      if (pendingEl) {
        // OVC: pdf - не восстанавливаем фокус для PDF блоков, чтобы не вызывать прокрутку
        if (pendingEl.closest('.audio-block, .doc-block--pdf, .doc-block--word, .slides-block, .table-block, .note-block--image')) {
          pendingCaretBlockId = null;
          return;
        }
        const editable = getEditableElement(pendingEl) || pendingEl;
        placeCaretAtEnd(editable);
      }
      pendingCaretBlockId = null;
    } else if (savedFocus) {
      // Восстанавливаем сохраненный фокус
      const targetBlockEl = canvas.querySelector(
        `[data-block-id="${savedFocus.blockId}"]`,
      );
      if (targetBlockEl) {
        // OVC: pdf - не восстанавливаем фокус для PDF блоков, чтобы не вызывать прокрутку
        if (targetBlockEl.closest('.audio-block, .doc-block--pdf, .doc-block--word, .slides-block, .table-block, .note-block--image')) {
          return;
        }
        const editable = getEditableElement(targetBlockEl) || targetBlockEl;
        requestAnimationFrame(() => {
          editable.focus();
          
          // Если было сохранено выделение - восстанавливаем его
          if (savedFocus.selection) {
            try {
              restoreSelection(editable, savedFocus.selection);
              // Устанавливаем защиту, чтобы выделение не сбросилось
              editable.dataset.justSelected = 'true';
              setTimeout(() => {
                delete editable.dataset.justSelected;
              }, 200);
            } catch (e) {
              // Если не удалось восстановить выделение, пытаемся восстановить курсор
              if (savedFocus.cursorOffset !== null) {
                restoreCursorPosition(editable, savedFocus.cursorOffset);
              } else {
                placeCaretAtEnd(editable);
              }
            }
          } else if (savedFocus.cursorOffset !== null) {
            // Восстанавливаем позицию курсора
            try {
              restoreCursorPosition(editable, savedFocus.cursorOffset);
            } catch (e) {
              // Если не удалось, ставим курсор в конец
              placeCaretAtEnd(editable);
            }
          } else {
            // Если позиция не была сохранена, ставим курсор в конец
            placeCaretAtEnd(editable);
          }
        });
      }
    }
  }

  // Вспомогательная функция для получения текста до курсора
  function getTextBeforeCursor(container, range) {
    try {
      const preRange = range.cloneRange();
      preRange.selectNodeContents(container);
      preRange.setEnd(range.startContainer, range.startOffset);
      return preRange.toString();
    } catch (e) {
      return '';
    }
  }

  // Восстановление позиции курсора по смещению
  function restoreCursorPosition(element, offset) {
    const selection = window.getSelection();
    if (!selection) return;

    const range = document.createRange();
    let currentOffset = 0;
    let targetNode = null;
    let targetOffset = 0;

    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_TEXT,
      null,
    );

    let node;
    while ((node = walker.nextNode())) {
      const nodeLength = node.textContent.length;
      if (currentOffset + nodeLength >= offset) {
        targetNode = node;
        targetOffset = offset - currentOffset;
        break;
      }
      currentOffset += nodeLength;
    }

    if (targetNode) {
      range.setStart(targetNode, Math.min(targetOffset, targetNode.textContent.length));
      range.setEnd(targetNode, Math.min(targetOffset, targetNode.textContent.length));
    } else {
      // Если не нашли узел, ставим в конец
      range.selectNodeContents(element);
      range.collapse(false);
    }

    selection.removeAllRanges();
    selection.addRange(range);
  }

  // Восстановление выделения по смещениям
  function restoreSelection(element, selectionData) {
    const selection = window.getSelection();
    if (!selection) return;

    const range = document.createRange();
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_TEXT,
      null,
    );

    let currentOffset = 0;
    let startNode = null;
    let startOffset = 0;
    let endNode = null;
    let endOffset = 0;

    let node;
    while ((node = walker.nextNode())) {
      const nodeLength = node.textContent.length;
      
      // Находим начало выделения
      if (!startNode && currentOffset + nodeLength >= selectionData.startOffset) {
        startNode = node;
        startOffset = selectionData.startOffset - currentOffset;
      }
      
      // Находим конец выделения
      if (!endNode && currentOffset + nodeLength >= selectionData.endOffset) {
        endNode = node;
        endOffset = selectionData.endOffset - currentOffset;
        break;
      }
      
      currentOffset += nodeLength;
    }

    if (startNode && endNode) {
      range.setStart(startNode, Math.min(startOffset, startNode.textContent.length));
      range.setEnd(endNode, Math.min(endOffset, endNode.textContent.length));
      selection.removeAllRanges();
      selection.addRange(range);
    } else {
      // Если не удалось восстановить, ставим курсор в конец
      range.selectNodeContents(element);
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }

  // ---- HYDRATE BLOCKS (ТОЧЕЧНЫЙ ФИКС) ----

  function hydrateBlocks() {
    if (!canvas) return;
    
    const blocks = canvas.querySelectorAll('[data-block-id]');
    if (blocks.length === 0) return;
    
    blocks.forEach((blockEl) => {
      if (!(blockEl instanceof HTMLElement)) return;

      // Специальная обработка для таблиц - ячейки обрабатываются отдельно
      const isTable = blockEl.dataset.blockRole === 'table' || blockEl.tagName === 'TABLE' || blockEl.dataset.blockType === 'table';
      
      // Создаем обертку и кнопки для всех блоков
      // setupDragAndDrop будет вызван внутри attachBlockControls
      const shell = attachBlockControls(blockEl);
     
      if (isTable) {
        hydrateTableCells(blockEl);
        return; // Не обрабатываем таблицу как обычный блок
      }

      // каждый блок создаётся renderNote как note-block + contenteditable
      // считаем этот элемент редактируемой зоной
      const editableEl = getEditableElement(blockEl) || blockEl;
      applyPlaceholderState(blockEl);

      if (!editableEl) return;

      // Чтобы не навешивать обработчики по 10 раз после каждого render()
      if (editableEl.dataset.editorBound === 'true') return;
      editableEl.dataset.editorBound = 'true';

      // Фокус в тексте блока → запоминаем, какой блок активен
      editableEl.addEventListener('focus', () => {
        focusedBlockId = blockEl.dataset.blockId;
        pendingCaretBlockId = null;
      });

      // Ввод текста → сохраняем в noteState, НЕ перерисовываем DOM
      editableEl.addEventListener('input', () => {
        updateBlockFromDom(blockEl, editableEl);
        applyPlaceholderState(blockEl);
        scheduleSave();
        rememberSelection();
      });

      // Любое перемещение каретки/набор → обновляем snapshot
      editableEl.addEventListener('keyup', () => {
        rememberSelection();
      });

      // Отслеживаем процесс выделения для защиты от сброса
      let isSelecting = false;
      let selectionStartTime = 0;
      let mouseDownTarget = null;
      
      // Объединенный обработчик mousedown для отслеживания выделения
      editableEl.addEventListener('mousedown', (event) => {
        mouseDownTarget = event.target;
        const isEmpty = !editableEl.textContent || editableEl.textContent.trim().length === 0;
        
        // Если элемент заполнен или уже в фокусе - начинаем отслеживать выделение
        if (!isEmpty || document.activeElement === editableEl) {
          isSelecting = true;
          selectionStartTime = Date.now();
        }
      }, { capture: true, passive: true });

      // Завершили выделение мышкой
      editableEl.addEventListener('mouseup', (event) => {
        rememberSelection();
        
        // СРАЗУ устанавливаем защиту при mouseup, чтобы защитить от click события
        // Это критично, так как click может сработать сразу после mouseup
        editableEl.dataset.justSelected = 'true';
        
        // Проверяем, было ли реальное выделение
        // Используем небольшую задержку, чтобы браузер успел обработать mouseup и установить выделение
        setTimeout(() => {
          const selection = window.getSelection();
          const hasSelection = selection && selection.rangeCount > 0 && !selection.isCollapsed;
          const selectionDuration = Date.now() - selectionStartTime;
          const wasMouseMoved = mouseDownTarget && event.target && mouseDownTarget !== event.target;
          
          // Если было выделение, продлеваем защиту на более длительное время
          if (hasSelection || wasMouseMoved || (isSelecting && selectionDuration > 50)) {
            // Защита уже установлена, просто продлеваем время
            setTimeout(() => {
              delete editableEl.dataset.justSelected;
            }, 500);
          } else {
            // Если это был просто клик без выделения, убираем защиту быстрее
            setTimeout(() => {
              delete editableEl.dataset.justSelected;
            }, 100);
          }
        }, 10);
        
        isSelecting = false;
        mouseDownTarget = null;
      }, { capture: true, passive: true });

      // Обработка клика и touch для установки фокуса
      // Для heading/paragraph editableEl === blockEl, поэтому нужна специальная логика
      const isDirectEditable = editableEl === blockEl;

      // Простой обработчик клика на блок - только для случаев, когда клик вне editable области
      if (!blockEl.dataset.blockClickBound) {
        blockEl.dataset.blockClickBound = 'true';
        blockEl.addEventListener('click', (event) => {
          const target = event.target;
          
          // Если только что было выделение - полностью игнорируем
          if (editableEl.dataset && editableEl.dataset.justSelected === 'true') {
            return;
          }
          
          // Если клик не по editable элементу и не внутри него - фокусируем
          // Но только если нет активного выделения текста
          if (target !== editableEl && !editableEl.contains(target)) {
            const selection = window.getSelection();
            const hasSelection = selection && selection.rangeCount > 0 && !selection.isCollapsed;
            // Фокусируем только если нет выделения
            if (!hasSelection) {
              focusEditable(editableEl);
            }
          }
        }, { passive: true });
      }

      // Минимальная обработка для прямых editable элементов (heading, paragraph)
      // Только для случаев, когда браузер не может установить фокус сам
      if (isDirectEditable && !editableEl.dataset.directEditableBound) {
        editableEl.dataset.directEditableBound = 'true';
        
        // Дополнительная обработка mousedown для пустых элементов
        // Используем обычную фазу (не capture), чтобы она выполнялась после отслеживания выделения
        editableEl.addEventListener('mousedown', (event) => {
          const isEmpty = !editableEl.textContent || editableEl.textContent.trim().length === 0;
          
          // Только для пустых элементов, которые не в фокусе
          if (isEmpty && document.activeElement !== editableEl) {
            // Не устанавливаем фокус, если только что было выделение
            if (editableEl.dataset.justSelected === 'true') {
              return;
            }
            
            // Проверяем, нет ли выделения
            const selection = window.getSelection();
            const hasSelection = selection && selection.rangeCount > 0 && !selection.isCollapsed;
            if (!hasSelection && !isSelecting) {
              event.preventDefault();
              requestAnimationFrame(() => {
                // Повторная проверка перед установкой фокуса
                if (!editableEl.dataset.justSelected) {
                  focusEditable(editableEl);
                }
              });
            }
          }
        }, { passive: false });

        // Обработка touchstart для мобильных (только для пустых)
        editableEl.addEventListener('touchstart', (event) => {
          const isEmpty = !editableEl.textContent || editableEl.textContent.trim().length === 0;
          if (isEmpty && document.activeElement !== editableEl) {
            event.preventDefault();
            requestAnimationFrame(() => {
              focusEditable(editableEl);
            });
          }
        }, { passive: false });

        // Для заполненных блоков - очень мягкая проверка после click
        // Только если браузер действительно не установил фокус
        editableEl.addEventListener('click', (event) => {
          // Сразу проверяем защитные флаги - если только что было выделение, выходим немедленно
          if (editableEl.dataset.justSelected === 'true') {
            return;
          }
          
          // Проверяем наличие выделения прямо сейчас
          const selection = window.getSelection();
          const hasSelection = selection && selection.rangeCount > 0 && !selection.isCollapsed;
          
          // Если есть выделение - полностью игнорируем этот клик
          if (hasSelection) {
            return;
          }
          
          // Длинная задержка, чтобы дать браузеру полностью обработать клик
          setTimeout(() => {
            // Повторно проверяем защитные флаги
            if (editableEl.dataset.justSelected === 'true') {
              return;
            }
            
            // Повторно проверяем выделение
            const currentSelection = window.getSelection();
            const currentHasSelection = currentSelection && currentSelection.rangeCount > 0 && !currentSelection.isCollapsed;
            if (currentHasSelection) {
              return;
            }
            
            // Проверяем только если элемент действительно не в фокусе
            // И клик был внутри editable элемента
            const clickedInside = event.target === editableEl || editableEl.contains(event.target);
            if (clickedInside && document.activeElement !== editableEl) {
              // Только теперь устанавливаем фокус
              editableEl.focus();
            }
          }, 100);
        }, { passive: true });
      }
    });

    if (!canvasClickBound) {
      canvas.addEventListener('click', onCanvasBlankClick);
      canvasClickBound = true;
    }
    
    // Добавляем обработчики drag для canvas (для drop в конец списка)
    if (!canvas.dataset.dragBound) {
      canvas.dataset.dragBound = 'true';
      
      canvas.addEventListener('dragover', (event) => {
        if (!dragState.activeId) return;
        // Проверяем, что мы не над каким-либо блоком
        const target = event.target;
        if (target.closest('.note-block-shell')) return;
        
        event.preventDefault();
        event.stopPropagation();
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = 'move';
        }
      });
      
      canvas.addEventListener('drop', (event) => {
        if (!dragState.activeId) return;
        // Проверяем, что мы не над каким-либо блоком
        const target = event.target;
        if (target.closest('.note-block-shell')) return;
        
        event.preventDefault();
        event.stopPropagation();
        
        // Находим последний блок
        const blocks = Array.from(canvas.querySelectorAll('.note-block-shell'));
        if (blocks.length === 0) return;
        
        const lastBlock = blocks[blocks.length - 1];
        const lastBlockEl = lastBlock.querySelector('[data-block-id]');
        if (!lastBlockEl) return;
        
        const lastBlockId = lastBlockEl.dataset.blockId;
        if (lastBlockId && lastBlockId !== dragState.activeId) {
          performDragReorder(dragState.activeId, lastBlockId, 'after');
        }
        clearDragState();
      });
    }
  }

  // ---- HYDRATE TABLE CELLS ----

  function hydrateTableCells(tableEl) {
    // Проверяем, не обработана ли таблица уже
    // ВАЖНО: не сбрасываем флаг при повторной обработке, чтобы не навешивать обработчики дважды
    if (tableEl.dataset.tableHydrated === 'true') {
      // Просто обновляем обработчики для новых ячеек, если они есть
      const cells = tableEl.querySelectorAll('td:not([data-cell-hydrated="true"]), th:not([data-cell-hydrated="true"])');
      if (cells.length > 0) {
        const blockId = tableEl.dataset.blockId;
        cells.forEach((cell) => {
          attachTableCellHandlers(cell, tableEl, blockId);
        });
      }
      return;
    }
    tableEl.dataset.tableHydrated = 'true';

    const cells = tableEl.querySelectorAll('td, th');
    const blockId = tableEl.dataset.blockId;

    cells.forEach((cell) => {
      attachTableCellHandlers(cell, tableEl, blockId);
    });
  }

  // Прикрепление обработчиков к ячейке таблицы
  function attachTableCellHandlers(cell, tableEl, blockId) {
    // Проверяем, не обработана ли ячейка уже
    if (cell.dataset.cellHydrated === 'true') return;
    cell.dataset.cellHydrated = 'true';

    // Обработчик ввода текста в ячейку
    cell.addEventListener('input', () => {
      updateTableFromDOM(tableEl);
      scheduleSave();
    });

    // Обработчик фокуса на ячейке
    cell.addEventListener('focus', () => {
      focusedBlockId = blockId;
      // Добавляем класс для визуальной обратной связи
      cell.classList.add('table-cell--active');
      // Показываем тулбар управления таблицей при необходимости
      showTableToolbar(tableEl);
    });

    // Обработчик потери фокуса
    cell.addEventListener('blur', () => {
      cell.classList.remove('table-cell--active');
    });

    // Навигация по таблице
    cell.addEventListener('keydown', (event) => {
      handleTableNavigation(event, cell, tableEl);
    });

    // Обработка клика для фокуса - не нужна, браузер сам обрабатывает клик
    // Но добавляем защиту от сброса выделения, как для обычных блоков
    cell.addEventListener('mouseup', () => {
      // Устанавливаем защиту от сброса выделения
      cell.dataset.justSelected = 'true';
      setTimeout(() => {
        delete cell.dataset.justSelected;
      }, 100);
    }, { passive: true });
  }

  // Обновление данных таблицы из DOM
  function updateTableFromDOM(tableEl) {
    const blockId = tableEl.dataset.blockId;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block || block.type !== 'table') return;

    const rows = Array.from(tableEl.querySelectorAll('tr'));
    block.data.rows = rows.map((tr) =>
      Array.from(tr.querySelectorAll('td, th')).map((td) => td.textContent ?? ''),
    );
  }

  // Навигация по таблице
  function handleTableNavigation(event, cell, tableEl) {
    const { key, shiftKey } = event;
    const currentRow = cell.parentElement;
    const currentRowIndex = Array.from(currentRow.parentElement.children).indexOf(currentRow);
    const currentCellIndex = Array.from(currentRow.children).indexOf(cell);
    const rows = Array.from(tableEl.querySelectorAll('tr'));
    const cellsInRow = Array.from(currentRow.children);

    let targetCell = null;

    switch (key) {
      case 'Tab':
        event.preventDefault();
        if (shiftKey) {
          // Shift+Tab - предыдущая ячейка
          if (currentCellIndex > 0) {
            targetCell = cellsInRow[currentCellIndex - 1];
          } else if (currentRowIndex > 0) {
            // Переход на последнюю ячейку предыдущей строки
            const prevRow = rows[currentRowIndex - 1];
            targetCell = prevRow.children[prevRow.children.length - 1];
          }
        } else {
          // Tab - следующая ячейка
          if (currentCellIndex < cellsInRow.length - 1) {
            targetCell = cellsInRow[currentCellIndex + 1];
          } else if (currentRowIndex < rows.length - 1) {
            // Переход на первую ячейку следующей строки
            const nextRow = rows[currentRowIndex + 1];
            targetCell = nextRow.children[0];
          }
        }
        break;

      case 'ArrowRight':
        if (event.ctrlKey || event.metaKey) return; // Разрешаем выделение текста
        if (currentCellIndex < cellsInRow.length - 1) {
          event.preventDefault();
          targetCell = cellsInRow[currentCellIndex + 1];
        }
        break;

      case 'ArrowLeft':
        if (event.ctrlKey || event.metaKey) return;
        if (currentCellIndex > 0) {
          event.preventDefault();
          targetCell = cellsInRow[currentCellIndex - 1];
        }
        break;

      case 'ArrowDown':
        if (event.ctrlKey || event.metaKey) return;
        if (currentRowIndex < rows.length - 1) {
          event.preventDefault();
          const nextRow = rows[currentRowIndex + 1];
          if (nextRow.children[currentCellIndex]) {
            targetCell = nextRow.children[currentCellIndex];
          }
        }
        break;

      case 'ArrowUp':
        if (event.ctrlKey || event.metaKey) return;
        if (currentRowIndex > 0) {
          event.preventDefault();
          const prevRow = rows[currentRowIndex - 1];
          if (prevRow.children[currentCellIndex]) {
            targetCell = prevRow.children[currentCellIndex];
          }
        }
        break;

      case 'Enter':
        // Enter - переход на следующую строку или создание новой
        if (event.shiftKey) {
          // Shift+Enter - новая строка внутри ячейки (стандартное поведение)
          return;
        }
        event.preventDefault();
        if (currentRowIndex < rows.length - 1) {
          const nextRow = rows[currentRowIndex + 1];
          if (nextRow.children[currentCellIndex]) {
            targetCell = nextRow.children[currentCellIndex];
          }
        } else {
          // Создаем новую строку
          addTableRow(tableEl, currentRowIndex + 1);
          // После добавления строки нужно найти новую ячейку
          requestAnimationFrame(() => {
            const newRows = Array.from(tableEl.querySelectorAll('tr'));
            if (newRows[currentRowIndex + 1]) {
              const newRow = newRows[currentRowIndex + 1];
              if (newRow.children[currentCellIndex]) {
                newRow.children[currentCellIndex].focus();
              }
            }
          });
          return;
        }
        break;
    }

    if (targetCell) {
      targetCell.focus();
      // Устанавливаем курсор в начало ячейки
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        range.selectNodeContents(targetCell);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
      }
    }
  }

  // Функция для отображения тулбара таблицы
  function showTableToolbar(tableEl) {
    // Пока просто заглушка, тулбар будет добавлен позже при необходимости
  }

  // Добавление строки в таблицу
  function addTableRow(tableEl, position = -1) {
    const blockId = tableEl.dataset.blockId;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block || block.type !== 'table') return;

    const rows = Array.from(tableEl.querySelectorAll('tr'));
    const colCount = rows[0] ? rows[0].children.length : 2;
    const newRow = Array(colCount).fill('');

    if (position === -1 || position >= block.data.rows.length) {
      block.data.rows.push(newRow);
    } else {
      block.data.rows.splice(position, 0, newRow);
    }

    // Сбрасываем флаг обработки для повторной гидратации
    tableEl.dataset.tableHydrated = 'false';
    render();
    scheduleSave();
  }

  // Удаление строки из таблицы
  function removeTableRow(tableEl, rowIndex) {
    const blockId = tableEl.dataset.blockId;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block || block.type !== 'table') return;

    if (block.data.rows.length <= 1) return; // Не удаляем последнюю строку

    block.data.rows.splice(rowIndex, 1);
    tableEl.dataset.tableHydrated = 'false';
    render();
    scheduleSave();
  }

  // Добавление столбца в таблицу
  function addTableColumn(tableEl, position = -1) {
    const blockId = tableEl.dataset.blockId;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block || block.type !== 'table') return;

    block.data.rows.forEach((row) => {
      if (position === -1 || position >= row.length) {
        row.push('');
      } else {
        row.splice(position, 0, '');
      }
    });

    tableEl.dataset.tableHydrated = 'false';
    render();
    scheduleSave();
  }

  // Удаление столбца из таблицы
  function removeTableColumn(tableEl, colIndex) {
    const blockId = tableEl.dataset.blockId;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block || block.type !== 'table') return;

    const minCols = Math.min(...block.data.rows.map((row) => row.length));
    if (minCols <= 1) return; // Не удаляем последний столбец

    block.data.rows.forEach((row) => {
      if (colIndex < row.length) {
        row.splice(colIndex, 1);
      }
    });

    tableEl.dataset.tableHydrated = 'false';
    render();
    scheduleSave();
  }

  // ---- UPDATE BLOCK FROM DOM ----

  function updateBlockFromDom(blockEl, editableEl) {
    const blockId = blockEl.dataset.blockId;
    const blockType = blockEl.dataset.blockType;
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block) return;

    const src = editableEl || blockEl;

    switch (blockType) {
      case 'heading':
        block.data.text = (src.textContent || '').trim();
        break;

      case 'paragraph': {
        const parts = extractRichTextParts(src);
        block.data.parts = parts;
        break;
      }

      case 'bulletList':
      case 'numberList': {
        const list =
          src.tagName === 'UL' || src.tagName === 'OL'
            ? src
            : src.querySelector('ul,ol') || src;

        block.data.items = Array.from(list.querySelectorAll('li')).map(
          (li) => ({
            text: (li.textContent || '').trim(),
          }),
        );
        break;
      }

      case 'quote':
        block.data.text = (src.textContent || '').trim();
        break;

      case 'table': {
        const table =
          src.tagName === 'TABLE' ? src : src.querySelector('table');
        if (!table) break;
        block.data.rows = Array.from(table.querySelectorAll('tr')).map((tr) =>
          Array.from(tr.querySelectorAll('td')).map(
            (td) => td.textContent ?? '',
          ),
        );
        break;
      }

      case 'summary': {
        const raw = src.innerText || '';
        block.data.text = raw.replace(/Сводка ·.+\n?/i, '').trim();
        break;
      }

      case 'todo': {
        const list =
          src.tagName === 'UL' || src.tagName === 'OL'
            ? src
            : src.querySelector('ul,ol') || src;

        block.data.items = Array.from(list.querySelectorAll('li')).map(
          (li, index) => ({
            id: block.data.items?.[index]?.id || uuid(),
            text: (li.textContent || '').trim(),
            done: block.data.items?.[index]?.done || false,
          }),
        );
        break;
      }

      default:
        break;
    }

    applyPlaceholderState(src);
  }

  // ---- INSERT / TRANSFORM ----

  function handleInsertBlock(block) {
    if (!block) return;
    const blocks = noteState.blocks.slice();

    if (focusedBlockId) {
      const index = blocks.findIndex((item) => item.id === focusedBlockId);
      if (index >= 0) {
        blocks.splice(index + 1, 0, block);
      } else {
        blocks.push(block);
      }
    } else {
      blocks.push(block);
    }

    noteState.blocks = blocks;
    focusedBlockId = block.id;
    pendingCaretBlockId = block.id;

    hints.push('Выделите текст, чтобы появилось форматирование.');
    render();
    scheduleSave();
  }

  function handleUploadedBlocks(blocks) {
    if (!Array.isArray(blocks) || !blocks.length) return;
    const normalized = blocks
      .filter(Boolean)
      .map((block) => ({
        id: block.id || uuid(),
        type: block.type,
        data: block.data || {},
      }));
    if (!normalized.length) return;
    noteState.blocks = noteState.blocks.concat(normalized);
    focusedBlockId = normalized.at(-1)?.id || null;
    pendingCaretBlockId = null;
    hints.push('Файл добавлен в конец заметки.');
    render();
    scheduleSave();
  }

  function handleTransformBlock(blockId, nextData) {
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block) return;

    block.type = nextData.type;
    block.data = nextData.data;
    focusedBlockId = blockId;
    pendingCaretBlockId = blockId;

    render();
    scheduleSave();
  }

  // OVC: pdf/table - обновление блока (например, изменение view)
  function handleBlockUpdate(blockId, updates) {
    const block = noteState.blocks.find((item) => item.id === blockId);
    if (!block) {
      console.warn('handleBlockUpdate: block not found', blockId);
      return;
    }

    // Обновляем данные блока
    const isMediaBlock =
      block.type === 'doc' ||
      block.type === 'audio' ||
      block.type === 'slides' ||
      block.type === 'video' ||
      block.type === 'youtube' ||
      (block.type === 'table' && block.data?.kind);

    if (updates.view !== undefined && isMediaBlock) {
      console.log('handleBlockUpdate: updating view', {
        blockId,
        oldView: block.data.view,
        newView: updates.view,
        blockType: block.type,
        blockData: block.data
      });
      block.data = { ...block.data, view: updates.view };

      // OVC: pdf - обновляем dataset в DOM, чтобы при следующем render() использовалось правильное значение
      const blockEl = canvas.querySelector(`[data-block-id="${blockId}"]`);
      if (blockEl && blockEl.dataset.view !== updates.view) {
        console.log('handleBlockUpdate: updating DOM dataset', { blockId, oldView: blockEl.dataset.view, newView: updates.view });
        blockEl.dataset.view = updates.view;
      }
    }

    if (updates.duration !== undefined && block.type === 'audio') {
      block.data = { ...block.data, duration: updates.duration };
    }

    if (updates.activeSheet !== undefined && block.type === 'table' && block.data?.kind) {
      block.data = { ...block.data, activeSheet: updates.activeSheet };
      const blockEl = canvas.querySelector(`[data-block-id="${blockId}"]`);
      if (blockEl) {
        blockEl.dataset.activeSheet = updates.activeSheet || '';
      }
    }

    // Сохраняем изменения (но НЕ перерисовываем, чтобы не потерять состояние PDF viewer)
    scheduleSave();
  }

  function toggleMediaBlockView(blockEl, kind) {
    if (!blockEl) return;
    const blockId = blockEl.dataset.blockId;
    if (!blockId) return;
    const nextView = blockEl.dataset.view === 'inline' ? 'cover' : 'inline';
    blockEl.dataset.view = nextView;
    const playerSelector = kind === 'video' ? '[data-role="video-player"]' : '[data-role="youtube-player"]';
    const coverSelector = kind === 'video' ? '[data-role="video-cover"]' : '[data-role="youtube-cover"]';

    const player = blockEl.querySelector(playerSelector);
    if (player) player.hidden = nextView !== 'inline';
    const cover = blockEl.querySelector(coverSelector);
    if (cover) cover.hidden = nextView === 'inline';
    
    // Для видео: при открытии плеера начинаем загрузку
    if (kind === 'video' && nextView === 'inline') {
      const video = player?.querySelector('video');
      if (video && video.preload === 'none') {
        video.preload = 'metadata';
        video.load();
      }
    }

    handleBlockUpdate(blockId, { view: nextView });
  }

  // ---- SAVE ----

  function scheduleSave() {
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(persistNote, SAVE_DEBOUNCE);
  }

  async function persistNote() {
    saveTimer = null;

    const payload = {
      title: noteState.title,
      blocks: noteState.blocks,
      styleTheme: noteState.styleTheme,
      layoutHints: noteState.layoutHints,
      passport: noteState.passport,
    };

    saveQueue.push(payload);
    if (saveQueue.length > 1) return;

    while (saveQueue.length) {
      const next = saveQueue[0];
      try {
        await fetch(`/api/notes/${noteState.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(next),
        });
      } catch (error) {
        console.error('Failed to save note', error);
      } finally {
        saveQueue.shift();
      }
    }
  }

  // ---- TITLE / THEME / LLM ----

  // OVC: title - защита от сброса текста при редактировании названия
  // Сохраняем флаг, что редактируется название, чтобы не вызывать render()
  let isEditingTitle = false;
  
  titleEl.addEventListener('focus', () => {
    isEditingTitle = true;
  });
  
  titleEl.addEventListener('blur', () => {
    isEditingTitle = false;
    // Обновляем title в noteState при потере фокуса
    noteState.title = titleEl.textContent.trim();
    scheduleSave();
  });
  
  titleEl.addEventListener('input', () => {
    // Обновляем title в noteState при вводе, но НЕ вызываем render()
    noteState.title = titleEl.textContent.trim();
    scheduleSave();
  });

  document.addEventListener('theme-change', (event) => {
    noteState.styleTheme = event.detail?.theme || 'clean';
    render();
    scheduleSave();
  });

  llmToggle?.addEventListener('change', () => {
    noteState.layoutHints = {
      ...noteState.layoutHints,
      autoLLM: llmToggle.checked,
    };
    scheduleSave();
  });

  // ---- BUTTONS ----

  shareBtn?.addEventListener('click', async () => {
    const choice = prompt('Введите формат экспорта: pdf или docx', 'pdf');
    if (!choice) return;
    if (choice.toLowerCase() === 'docx') {
      window.open(`/api/export/docx/${noteState.id}`, '_blank');
    } else {
      window.print();
    }
  });

  backBtn?.addEventListener('click', () => {
    window.location.href = '/notes';
  });

  infoBtn?.addEventListener('click', () => {
    const hidden = inspectorEl.getAttribute('aria-hidden') !== 'false';
    inspectorEl.setAttribute('aria-hidden', hidden ? 'false' : 'true');
    if (hidden) {
      inspector.onOpen?.(noteState);
    }
  });

  // ---- LAYOUT HINTS / LINKS ----

  function handleLayoutHintUpdate(key, rawValue) {
    const numeric = Number.parseFloat(rawValue);
    const value = Number.isNaN(numeric)
      ? rawValue
      : Math.max(0.3, Math.min(6, numeric));

    noteState.layoutHints = {
      ...noteState.layoutHints,
      [key]: value,
    };
    scheduleSave();
  }

  async function fetchLinkableNotes() {
    const res = await fetch('/api/notes?limit=100');
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    if (!Array.isArray(data?.items)) return [];
    return data.items.map((item) => ({
      id: item.id,
      title: item.title,
    }));
  }

  async function createManualLink({ toId, reason }) {
    const noteId = await ensureNote();
    if (!toId) throw new Error('Не выбрана цель связи');
    if (toId === noteId) throw new Error('Нельзя связать заметку саму с собой');

    const normalizedReason = (reason || '').trim() || 'manual';
    const payload = {
      draft: [
        {
          type: 'add_link',
          noteId,
          fromId: noteId,
          toId,
          reason: normalizedReason,
          confidence: 0.9,
        },
      ],
    };

    const res = await fetch('/api/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(await res.text());
    const result = await res.json();
    if (!result.applied) {
      throw new Error('Связь уже существует');
    }

    await refreshNoteState();
  }

  // ---- CANVAS ----

  function onCanvasBlankClick(event) {
    if (event.button !== 0) return;
    // Игнорируем клики по кнопкам и их дочерним элементам
    if (event.target.closest('.floating-actions')) return;
    if (event.target.closest('[data-block-id]')) return;
    // OVC: files - игнорируем клики по файловым блокам
    if (event.target.closest('.audio-block, .doc-block--pdf, .doc-block--word, .slides-block, .table-block, .note-block--image')) return;
    if (event.target.closest('.pdf-pages')) return;
    if (event.target.closest('.pdf-page')) return;
    if (event.target.closest('.pdf-page img')) return;
    focusTailBlock();
  }

  function focusTailBlock() {
    const lastBlock = canvas.querySelector('[data-block-id]:last-of-type');
    if (lastBlock) {
      // OVC: pdf - не фокусируем, если последний блок - это PDF блок
      if (lastBlock.closest('.audio-block, .doc-block--pdf, .doc-block--word, .slides-block, .table-block, .note-block--image')) {
        return; // Не фокусируем PDF блоки
      }
      const editable = getEditableElement(lastBlock) || lastBlock;
      focusedBlockId = lastBlock.dataset.blockId;
      placeCaretAtEnd(editable);
      return;
    }

    const fallback = {
      id: uuid(),
      type: 'paragraph',
      data: { parts: [{ text: '' }] },
    };
    const nextBlocks = Array.isArray(noteState.blocks)
      ? noteState.blocks.slice()
      : [];
    nextBlocks.push(fallback);
    noteState.blocks = nextBlocks;
    focusedBlockId = fallback.id;
    pendingCaretBlockId = fallback.id;

    render();
    scheduleSave();
  }

  function wrapBlockWithShell(blockEl) {
    if (!blockEl) {
      console.error('[wrapBlockWithShell] blockEl отсутствует');
      return null;
    }
    
    if (!blockEl.parentElement) {
      console.error('[wrapBlockWithShell] blockEl.parentElement отсутствует для:', blockEl);
      return null;
    }
    
    // Если блок уже в обертке, возвращаем обертку
    const currentParent = blockEl.parentElement;
    if (currentParent.classList && currentParent.classList.contains('note-block-shell')) {
      return currentParent;
    }
    
    // Создаем обертку и перемещаем блок в неё
    const shell = document.createElement('div');
    shell.className = 'note-block-shell';
    const parent = blockEl.parentElement;
    
    try {
      // Вставляем обертку ПЕРЕД блоком, затем перемещаем блок в обертку
      parent.insertBefore(shell, blockEl);
      shell.appendChild(blockEl);
      return shell;
    } catch (error) {
      console.error('[wrapBlockWithShell] Ошибка при создании обертки:', error);
      return null;
    }
  }

  function attachBlockControls(blockEl) {
    if (!blockEl || !blockEl.dataset.blockId) return null;
    
    const shell = wrapBlockWithShell(blockEl);
    if (!shell) return null;
    
    // Проверяем, не созданы ли кнопки уже
    if (shell.dataset.actionsBound === 'true') {
      return shell;
    }
    
    // Проверяем, нет ли уже кнопок в обертке
    const existingActions = shell.querySelector('.block-actions');
    if (existingActions) {
      shell.dataset.actionsBound = 'true';
      return shell;
    }
    
    const actions = document.createElement('div');
    actions.className = 'block-actions';
    const buttons = [
      { action: 'drag-handle', label: '↕', title: 'Перетащить блок', handle: true },
      { action: 'insert-before', label: '＋↑', title: 'Вставить блок выше' },
      { action: 'insert-after', label: '＋↓', title: 'Вставить блок ниже' },
      { action: 'move-up', label: '↑', title: 'Переместить вверх' },
      { action: 'move-down', label: '↓', title: 'Переместить вниз' },
      { action: 'delete', label: '✕', title: 'Удалить блок' },
    ];

    buttons.forEach(({ action, label, title }) => {
      if (action === 'drag-handle') {
        // Для handle используем span вместо button, чтобы drag работал
        const handle = document.createElement('span');
        handle.className = 'block-action-handle';
        handle.dataset.action = action;
        handle.textContent = label;
        handle.title = title;
        handle.setAttribute('contenteditable', 'false');
        handle.setAttribute('draggable', 'true');
        handle.style.cssText = 'pointer-events: auto; cursor: grab; user-select: none;';
        handle.setAttribute('role', 'button');
        handle.setAttribute('tabindex', '-1');
        actions.appendChild(handle);
      } else {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.dataset.action = action;
        btn.textContent = label;
        btn.title = title;
        btn.setAttribute('contenteditable', 'false');
        btn.tabIndex = -1;
        btn.style.cssText = 'pointer-events: auto;';
        btn.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          handleBlockAction(blockEl.dataset.blockId, action);
        });
        actions.appendChild(btn);
      }
    });

    // Добавляем кнопки в начало обертки (перед блоком)
    // Блок должен быть уже в обертке после wrapBlockWithShell
    shell.insertBefore(actions, shell.firstChild);
    shell.dataset.actionsBound = 'true';
    
    // Добавляем обработчики для показа/скрытия кнопок при выделении блока
    setupBlockSelectionHandlers(shell, blockEl);
    
    // Настраиваем drag and drop после создания кнопок
    setupDragAndDrop(shell, blockEl.dataset.blockId);
    
    return shell;
  }
  
  // Функция для управления видимостью кнопок при выделении блока
  function setupBlockSelectionHandlers(shell, blockEl) {
    // Пустая функция - вся логика теперь в initGlobalBlockHandlers
  }
  
  // Глобальный обработчик для выделения блоков - добавляется один раз на canvas
  let globalBlockHandlersAdded = false;
  function initGlobalBlockHandlers() {
    if (globalBlockHandlersAdded || !canvas) return;
    globalBlockHandlersAdded = true;
    
    // Функция выделения блока
    function selectBlock(shell) {
      if (!shell) return;
      // Снимаем выделение со всех других блоков
      canvas.querySelectorAll('.note-block-shell.selected').forEach(s => {
        if (s !== shell) {
          s.classList.remove('selected');
          s.dataset.selected = 'false';
        }
      });
      // Выделяем текущий блок
      shell.classList.add('selected');
      shell.dataset.selected = 'true';
    }
    
    // Функция снятия выделения со всех блоков
    function deselectAllBlocks() {
      canvas.querySelectorAll('.note-block-shell.selected').forEach(s => {
        s.classList.remove('selected');
        s.dataset.selected = 'false';
      });
    }
    
    // Обработчик на canvas - делегирование событий
    canvas.addEventListener('mousedown', (event) => {
      const shell = event.target.closest('.note-block-shell');
      if (shell && !event.target.closest('.block-actions')) {
        selectBlock(shell);
      }
    }, { capture: true });
    
    canvas.addEventListener('click', (event) => {
      const shell = event.target.closest('.note-block-shell');
      if (shell && !event.target.closest('.block-actions')) {
        selectBlock(shell);
      }
    }, { capture: true });
    
    // Обработчик фокуса для текстовых блоков
    canvas.addEventListener('focusin', (event) => {
      const shell = event.target.closest('.note-block-shell');
      if (shell) {
        selectBlock(shell);
      }
    }, { capture: true });
    
    // Снимаем выделение при клике вне canvas
    document.addEventListener('mousedown', (event) => {
      if (!canvas.contains(event.target)) {
        deselectAllBlocks();
      }
    });
  }

  function setupDragAndDrop(shell, blockId) {
    if (!shell || !blockId) return;
    if (shell.dataset.dragBound === 'true') return;
    shell.dataset.dragBound = 'true';

    // Находим handle элемент внутри shell
    const handle = shell.querySelector('.block-action-handle');
    if (!handle) {
      // Handle должен быть создан в attachBlockControls
      // Если его нет, значит что-то пошло не так
      console.warn('[setupDragAndDrop] Handle не найден для блока:', blockId);
      return;
    }

    // Убеждаемся, что handle draggable и только он
    handle.draggable = true;
    handle.setAttribute('draggable', 'true');
    
    // Предотвращаем drag для всех других элементов в shell
    shell.querySelectorAll('*').forEach((el) => {
      if (el !== handle) {
        el.draggable = false;
        if (el.setAttribute) {
          el.setAttribute('draggable', 'false');
        }
      }
    });

    // Обработчик начала перетаскивания
    handle.addEventListener('dragstart', (event) => {
      dragState.activeId = blockId;
      shell.classList.add('dragging');
      
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', blockId);
        // Используем пустое изображение, чтобы браузер использовал стандартный drag image
        const emptyImg = new Image();
        emptyImg.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
        event.dataTransfer.setDragImage(emptyImg, 0, 0);
      }
      event.stopPropagation();
    });

    // Обработчик окончания перетаскивания
    handle.addEventListener('dragend', (event) => {
      clearDragState();
    });

    shell.addEventListener('dragover', (event) => {
      if (!dragState.activeId || dragState.activeId === blockId) return;
      event.preventDefault();
      event.stopPropagation();
      
      const rect = shell.getBoundingClientRect();
      const mouseY = event.clientY;
      const shellMiddle = rect.top + rect.height / 2;
      const position = mouseY < shellMiddle ? 'before' : 'after';
      
      updateDropIndicator(shell, position);
      dragState.overId = blockId;
      dragState.position = position;
      
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'move';
      }
    });

    shell.addEventListener('dragleave', (event) => {
      // Проверяем, что мы действительно покидаем shell, а не переходим в дочерний элемент
      const relatedTarget = event.relatedTarget;
      if (relatedTarget && shell.contains(relatedTarget)) return;
      
      shell.classList.remove('drop-before', 'drop-after');
      if (dragState.overId === blockId) {
        dragState.overId = null;
        dragState.position = null;
      }
    });

    shell.addEventListener('drop', (event) => {
      event.preventDefault();
      event.stopPropagation();
      
      if (!dragState.activeId || dragState.activeId === blockId) {
        clearDragState();
        return;
      }
      
      const position = dragState.position || 'after';
      performDragReorder(dragState.activeId, blockId, position);
      clearDragState();
    });
  }


  function handleBlockAction(blockId, action) {
    if (!blockId) return;
    const blocks = Array.isArray(noteState.blocks)
      ? [...noteState.blocks]
      : [];
    const index = blocks.findIndex((block) => block.id === blockId);
    if (index === -1) return;

    const commit = (nextBlocks, focusId) => {
      noteState.blocks = nextBlocks;
      if (focusId) {
        pendingCaretBlockId = focusId;
      }
      render();
      scheduleSave();
    };

    switch (action) {
      case 'delete': {
        if (blocks.length === 1) {
          const fallback = createBlankParagraphBlock();
          commit([fallback], fallback.id);
          return;
        }
        blocks.splice(index, 1);
        const nextFocus = blocks[Math.min(index, blocks.length - 1)]?.id;
        commit(blocks, nextFocus);
        return;
      }

      case 'move-up': {
        if (index === 0) return;
        [blocks[index - 1], blocks[index]] = [
          blocks[index],
          blocks[index - 1],
        ];
        commit(blocks, blockId);
        return;
      }

      case 'move-down': {
        if (index === blocks.length - 1) return;
        [blocks[index + 1], blocks[index]] = [
          blocks[index],
          blocks[index + 1],
        ];
        commit(blocks, blockId);
        return;
      }

      case 'insert-before': {
        const newBlock = createBlankParagraphBlock();
        blocks.splice(index, 0, newBlock);
        commit(blocks, newBlock.id);
        return;
      }

      case 'insert-after': {
        const newBlock = createBlankParagraphBlock();
        blocks.splice(index + 1, 0, newBlock);
        commit(blocks, newBlock.id);
        return;
      }

      default:
        return;
    }
  }

  function createBlankParagraphBlock() {
    return {
      id: uuid(),
      type: 'paragraph',
      data: { parts: [{ text: '' }] },
    };
  }

  // Функция для обновления визуального индикатора места drop
  function updateDropIndicator(shell, position) {
    if (!shell) return;
    // Убираем все индикаторы с других блоков
    document.querySelectorAll('.note-block-shell').forEach((s) => {
      if (s !== shell) {
        s.classList.remove('drop-before', 'drop-after');
      }
    });
    // Добавляем индикатор на текущий shell
    shell.classList.remove('drop-before', 'drop-after');
    shell.classList.add(position === 'before' ? 'drop-before' : 'drop-after');
  }

  function clearDragState() {
    dragState.activeId = null;
    dragState.overId = null;
    dragState.position = null;
    document
      .querySelectorAll('.note-block-shell')
      .forEach((shell) => shell.classList.remove('dragging', 'drop-before', 'drop-after'));
  }

  function performDragReorder(sourceId, targetId, position) {
    if (!sourceId || !targetId || sourceId === targetId) return;
    const blocks = Array.isArray(noteState.blocks) ? [...noteState.blocks] : [];
    const fromIndex = blocks.findIndex((block) => block.id === sourceId);
    let targetIndex = blocks.findIndex((block) => block.id === targetId);
    if (fromIndex === -1 || targetIndex === -1) return;

    const [moved] = blocks.splice(fromIndex, 1);
    targetIndex = blocks.findIndex((block) => block.id === targetId);
    if (targetIndex === -1) targetIndex = blocks.length;
    if (position === 'after') {
      targetIndex += 1;
    }
    blocks.splice(targetIndex, 0, moved);

    noteState.blocks = blocks;
    pendingCaretBlockId = sourceId;
    render();
    scheduleSave();
  }

  function ensureEditableFallback() {
    // Больше не создаем placeholder блок - вместо этого показываем кнопки в центре
    // Функция оставлена для совместимости, но ничего не делает
  }

  function updateFloatingActionsOffset() {
    if (!floatingActions || !canvas) return;
    const blockCount = canvas.querySelectorAll('[data-block-id]').length;
    const isEmpty = blockCount === 0;
    
    if (isEmpty) {
      // Если заметка пустая - центрируем кнопки
      floatingActions.classList.add('floating-actions--centered');
      floatingActions.style.setProperty('--floating-actions-offset', 'auto');
    } else {
      // Если есть блоки - показываем кнопки справа с динамическим отступом
      floatingActions.classList.remove('floating-actions--centered');
      const dynamicOffset = Math.min(18 + blockCount * 6, 140);
      floatingActions.style.setProperty(
        '--floating-actions-offset',
        `${dynamicOffset}px`,
      );
    }
  }

  // ---- UTILS ----

  function focusEditable(element) {
    if (!element) return;
    
    // Проверяем защитный флаг - если только что было выделение, не трогаем
    if (element.dataset && element.dataset.justSelected === 'true') {
      return;
    }
    
    const selection = window.getSelection();
    
    // Проверяем, есть ли активное выделение текста внутри элемента
    if (selection && selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      const anchorNode = selection.anchorNode;
      const focusNode = selection.focusNode;
      const hasValidSelection = 
        anchorNode && focusNode &&
        (element.contains(anchorNode) || anchorNode === element) &&
        (element.contains(focusNode) || focusNode === element) &&
        !selection.isCollapsed;

      // Если есть валидное выделение - НИ В КОЕМ СЛУЧАЕ не трогаем его
      // Это критично для сохранения выделения пользователя
      if (hasValidSelection) {
        // Если элемент уже в фокусе - не делаем ничего
        if (document.activeElement === element) {
          return;
        }
        
        // Если элемент не в фокусе, но есть выделение - устанавливаем фокус ОЧЕНЬ аккуратно
        // Сохраняем выделение и восстанавливаем его после focus
        try {
          const savedRange = range.cloneRange();
          // ВАЖНО: Не используем preventScroll, чтобы не мешать браузеру
          element.focus({ preventScroll: false });
          
          // Немедленно восстанавливаем выделение
          requestAnimationFrame(() => {
            try {
              const currentSelection = window.getSelection();
              if (currentSelection) {
                // Проверяем, что выделение не было потеряно
                if (currentSelection.rangeCount === 0 || currentSelection.isCollapsed) {
                  currentSelection.removeAllRanges();
                  currentSelection.addRange(savedRange);
                }
              }
            } catch (e) {
              // Игнорируем ошибки восстановления
            }
          });
          return;
        } catch (e) {
          // Если не удалось сохранить - не устанавливаем фокус, чтобы не сбросить выделение
          return;
        }
      }
    }
    
    // Если нет Selection API или нет выделения - устанавливаем фокус обычным способом
    if (!selection) {
      element.focus();
      return;
    }

    // Принудительно устанавливаем фокус только если элемент не в фокусе
    if (document.activeElement !== element) {
      element.focus({ preventScroll: false });
    }

    // Устанавливаем курсор в конец элемента
    try {
      const range = document.createRange();
      
      // Находим последний текстовый узел или используем сам элемент
      let targetNode = element;
      let lastTextNode = null;
      
      const findLastTextNode = (node) => {
        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0) {
          lastTextNode = node;
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          // Ищем в дочерних элементах с конца
          for (let i = node.childNodes.length - 1; i >= 0; i--) {
            findLastTextNode(node.childNodes[i]);
            if (lastTextNode) break;
          }
        }
      };
      
      findLastTextNode(element);
      
      if (lastTextNode) {
        // Устанавливаем курсор в конец последнего текстового узла
        range.setStart(lastTextNode, lastTextNode.textContent.length);
        range.setEnd(lastTextNode, lastTextNode.textContent.length);
      } else if (element.childNodes.length > 0) {
        // Если есть дочерние элементы, но нет текстовых узлов, устанавливаем курсор в конец
        const lastChild = element.childNodes[element.childNodes.length - 1];
        if (lastChild.nodeType === Node.ELEMENT_NODE) {
          range.setStartAfter(lastChild);
          range.setEndAfter(lastChild);
        } else {
          range.selectNodeContents(element);
          range.collapse(false);
        }
      } else {
        // Элемент полностью пустой - устанавливаем курсор в начало
        range.setStart(element, 0);
        range.setEnd(element, 0);
      }
      
      selection.removeAllRanges();
      selection.addRange(range);
    } catch (error) {
      // Fallback: просто фокусируем элемент
      console.warn('Failed to set cursor position:', error);
      element.focus();
    }
  }

  function getEditableElement(blockEl) {
    if (!blockEl) return null;
    const inner =
      blockEl.querySelector('.ovc-block-content[contenteditable="true"]') ||
      blockEl.querySelector('.note-editable[contenteditable="true"]');
    if (inner) return inner;
    if (blockEl.isContentEditable) return blockEl;
    return blockEl.querySelector('[contenteditable="true"]');
  }

  function placeCaretAtEnd(element) {
    if (!element) return;
    if (typeof element.focus === 'function') {
      element.focus({ preventScroll: true });
    }
    const selection = window.getSelection();
    if (!selection) return;
    const range = document.createRange();
    let target = element;
    if (target.matches('ul, ol')) {
      const lastItem = target.querySelector('li:last-child');
      if (lastItem) target = lastItem;
    }
    range.selectNodeContents(target);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
    rememberSelection();
  }

  function stripPlaceholder(value, allowPlaceholderCheck = false) {
    if (value === null || value === undefined) return '';
    const stringValue = typeof value === 'string' ? value : String(value);
    const trimmed = stringValue.trim();
    if (!trimmed) return '';
    if (allowPlaceholderCheck && PLACEHOLDER_STRINGS.has(trimmed)) {
      return '';
    }
    return stringValue;
  }

  function cleanIncomingBlocks(blocks) {
    if (!Array.isArray(blocks)) return [];
    return blocks.map((block) => {
      if (!block || typeof block !== 'object') return block;
      const data = { ...(block.data || {}) };

      if (block.type === 'heading') {
        data.text = stripPlaceholder(data.text || '', true);
        return { ...block, data };
      }

      if (block.type === 'paragraph') {
        const rawParts = Array.isArray(data.parts)
          ? data.parts
          : [{ text: data.text || '' }];

        const parts = rawParts
          .map((part) => ({
            text: stripPlaceholder(part?.text || '', true),
            annotations: sanitizeAnnotations(part?.annotations),
          }))
          .filter((part) => part.text !== '');

        data.parts = parts.length ? parts : [{ text: '' }];
        delete data.text;
        return { ...block, data };
      }

      return { ...block, data };
    });
  }

  function sanitizeAnnotations(annotations) {
    if (!annotations || typeof annotations !== 'object') return undefined;
    const clean = {};
    if (annotations.bold) clean.bold = true;
    if (annotations.italic) clean.italic = true;
    if (annotations.underline) clean.underline = true;
    if (annotations.strike) clean.strike = true;
    if (annotations.code) clean.code = true;
    if (annotations.href) clean.href = String(annotations.href);
    return Object.keys(clean).length ? clean : undefined;
  }

  function extractRichTextParts(blockEl) {
    const segments = [];

    const walk = (node, marks) => {
      if (!node) return;

      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent ?? '';
        if (text.length === 0) return;
        segments.push({
          text,
          annotations: Object.keys(marks).length ? { ...marks } : undefined,
        });
        return;
      }

      if (node.nodeType !== Node.ELEMENT_NODE) return;

      if (node.tagName?.toLowerCase() === 'br') {
        segments.push({
          text: '\n',
          annotations: Object.keys(marks).length ? { ...marks } : undefined,
        });
        return;
      }

      const nextMarks = accumulateMarks(node, marks);
      node.childNodes.forEach((child) => walk(child, nextMarks));
    };

    blockEl.childNodes.forEach((child) => walk(child, {}));

    const merged = mergeSegments(segments).map((part) =>
      part.annotations ? part : { text: part.text },
    );

    return merged.length ? merged : [{ text: '' }];
  }

  function accumulateMarks(element, marks) {
    const tag = element.tagName?.toLowerCase?.() || '';
    const next = { ...marks };

    if (tag === 'b' || tag === 'strong') next.bold = true;
    if (tag === 'i' || tag === 'em') next.italic = true;
    if (tag === 'u') next.underline = true;
    if (tag === 's' || tag === 'del' || tag === 'strike') next.strike = true;
    if (tag === 'code') next.code = true;

    if (tag === 'a' && element.getAttribute) {
      const href = element.getAttribute('href');
      if (href) next.href = href;
    }

    const style = element.getAttribute?.('style') || '';
    if (style) {
      const lower = style.toLowerCase();
      if (lower.includes('font-weight')) {
        const m = lower.match(/font-weight\\s*:\\s*([0-9]+)/);
        if (m && parseInt(m[1], 10) >= 500) next.bold = true;
      }
      if (lower.includes('font-style') && lower.includes('italic')) {
        next.italic = true;
      }
      if (lower.includes('text-decoration')) {
        if (lower.includes('underline')) next.underline = true;
        if (lower.includes('line-through')) next.strike = true;
      }
    }

    return next;
  }

  function mergeSegments(segments) {
    if (!segments.length) return segments;
    const merged = [];
    segments.forEach((segment) => {
      const prev = merged[merged.length - 1];
      if (
        prev &&
        shallowEqualAnnotations(prev.annotations, segment.annotations)
      ) {
        prev.text += segment.text;
      } else {
        merged.push({
          text: segment.text,
          annotations: segment.annotations,
        });
      }
    });
    return merged;
  }

  function shallowEqualAnnotations(a, b) {
    if (!a && !b) return true;
    if (!a || !b) return false;
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    return keysA.every((key) => Boolean(a[key]) === Boolean(b[key]));
  }

  function applyPlaceholderState(blockEl) {
    if (!blockEl || !blockEl.dataset) return;
    if (blockEl.dataset.blockRole === 'table' || blockEl.tagName === 'TABLE') {
      return;
    }
    if (!blockEl.dataset.placeholder) return;
    const text = (blockEl.textContent || '').replace(/\u200B/g, '').trim();
    if (text.length === 0) {
      blockEl.dataset.empty = 'true';
    } else {
      delete blockEl.dataset.empty;
    }
  }

  // ---- INIT ----
  
  // Инициализируем глобальные обработчики для выделения блоков
  initGlobalBlockHandlers();

  loadNote().catch((error) =>
    console.error('Unable to load note', error),
  );
});
