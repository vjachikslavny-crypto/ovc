import { renderNote } from './blocks_render.js';
import { initToolbar, clearSelectionSnapshot, rememberSelection } from './toolbar.js';
import { initInlineBubble } from './inline_bubble.js';
import { initPalette } from './palette.js';
import { initSmartInsert } from './smart_insert.js';
import { initInspector } from './inspector.js';
import { initHints } from './hints.js';
import { uuid } from './utils.js';

const SAVE_DEBOUNCE = 600;
const PLACEHOLDER_STRINGS = new Set(['Новый заголовок', 'Новый абзац']);

document.addEventListener('DOMContentLoaded', () => {
  const editorEl = document.querySelector('.editor');
  if (!editorEl) return;

  const canvas = document.getElementById('note-blocks');
  const titleEl = document.getElementById('note-title');
  const shareBtn = document.getElementById('note-share');
  const backBtn = document.getElementById('nav-back');
  const infoBtn = document.getElementById('note-info');
  const paletteEl = document.getElementById('block-palette');
  const fabPlus = document.getElementById('fab-plus');
  const fabVoice = document.getElementById('fab-voice');
  const fabAttach = document.getElementById('fab-attach');
  const fileInput = document.getElementById('file-input');
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
    // Сохраняем информацию о текущем фокусе и выделении перед перерисовкой
    const activeElement = document.activeElement;
    let savedFocus = null;
    let savedSelection = null;
    
    if (activeElement && canvas.contains(activeElement)) {
      // Находим блок, который был в фокусе
      const focusedBlockEl = activeElement.closest('[data-block-id]');
      if (focusedBlockEl) {
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

    titleEl.textContent = noteState.title || 'Без названия';
    renderNote(canvas, noteState, document.body.dataset.theme || 'clean');
    clearSelectionSnapshot();
    hydrateBlocks();
    inspector.update(noteState);

    if (llmToggle) {
      llmToggle.checked = Boolean(noteState.layoutHints?.autoLLM);
    }

    // Восстанавливаем фокус после перерисовки
    if (pendingCaretBlockId) {
      const pendingEl = canvas.querySelector(
        `[data-block-id="${pendingCaretBlockId}"]`,
      );
      if (pendingEl) {
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
    canvas.querySelectorAll('[data-block-id]').forEach((blockEl) => {
      if (!(blockEl instanceof HTMLElement)) return;

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

  titleEl.addEventListener('input', () => {
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

  fabVoice?.addEventListener('click', async () => {
    const text = prompt('Продиктуйте заметку (ввод текстом)');
    if (!text) return;
    handleInsertBlock({
      id: uuid(),
      type: 'paragraph',
      data: { parts: [{ text }] },
    });
  });

  fabAttach?.addEventListener('click', () => fileInput?.click());

  fileInput?.addEventListener('change', (event) => {
    const files = Array.from(event.target.files || []);
    files.forEach((file) => {
      const url = URL.createObjectURL(file);
      handleInsertBlock({
        id: uuid(),
        type: 'image',
        data: { src: url, alt: file.name, caption: '' },
      });
    });
    fileInput.value = '';
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
    if (event.target.closest('[data-block-id]')) return;
    focusTailBlock();
  }

  function focusTailBlock() {
    const lastBlock = canvas.querySelector('[data-block-id]:last-of-type');
    if (lastBlock) {
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
    if (blockEl.isContentEditable) return blockEl;
    return blockEl.querySelector('.note-editable[contenteditable="true"]')
      || blockEl.querySelector('[contenteditable="true"]');
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
    if (!blockEl.dataset.placeholder) return;
    const text = (blockEl.textContent || '').replace(/\u200B/g, '').trim();
    if (text.length === 0) {
      blockEl.dataset.empty = 'true';
    } else {
      delete blockEl.dataset.empty;
    }
  }

  // ---- INIT ----

  loadNote().catch((error) =>
    console.error('Unable to load note', error),
  );
});
