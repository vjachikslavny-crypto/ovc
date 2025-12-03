import { uuid } from './utils.js';

export function initPalette({ paletteEl, triggerEl, onInsert }) {
  if (!paletteEl || !triggerEl) return;

  const close = () => paletteEl.setAttribute('aria-hidden', 'true');
  const open = () => paletteEl.setAttribute('aria-hidden', 'false');
  const isOpen = () => paletteEl.getAttribute('aria-hidden') === 'false';

  triggerEl.addEventListener('click', (event) => {
    event.preventDefault();
    const isHidden = paletteEl.getAttribute('aria-hidden') !== 'false';
    if (isHidden) {
      open();
    } else {
      close();
    }
  });

  paletteEl.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-block]');
    if (!button) return;
    const blockType = button.dataset.block;
    
    // Для таблицы используем асинхронный выбор размера
    if (blockType === 'table') {
      close(); // Закрываем палитру сразу
      const payload = await showTableSizePicker();
      if (payload && typeof onInsert === 'function') {
        onInsert(payload);
      }
      return;
    }
    
    const payload = buildBlock(blockType, button.dataset);
    if (payload && typeof onInsert === 'function') {
      onInsert(payload);
    }
    close();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') close();
  });

  // Закрываем палитру при клике/тапе вне её области
  const handleOutsidePointer = (event) => {
    if (!isOpen()) return;
    const target = event.target;
    if (!target) return;
    if (paletteEl.contains(target) || triggerEl.contains(target)) return;
    close();
  };

  // Используем mousedown в capture-режиме, чтобы срабатывать раньше stopPropagation
  document.addEventListener('mousedown', handleOutsidePointer, { capture: true });
  document.addEventListener('touchstart', handleOutsidePointer, { capture: true });
}

function buildBlock(type, dataset = {}) {
  const id = uuid();
  switch (type) {
    case 'heading':
      return { id, type: 'heading', data: { level: parseInt(dataset.level || '1', 10), text: '' } };
    case 'paragraph':
      return { id, type: 'paragraph', data: { parts: [{ text: '' }] } };
    case 'bulletList':
      return { id, type: 'bulletList', data: { items: [{ text: 'Первый пункт' }] } };
    case 'quote':
      return { id, type: 'quote', data: { text: 'Цитата', cite: '' } };
    // case 'table' обрабатывается отдельно в initPalette
    case 'table':
      // Этот case не должен вызываться, так как таблица обрабатывается асинхронно
      return null;
    case 'todo':
      return { id, type: 'todo', data: { items: [{ id: uuid(), text: 'Задача', done: false }] } };
    case 'summary':
      return { id, type: 'summary', data: { dateISO: new Date().toISOString().split('T')[0], text: 'Краткая сводка' } };
    case 'divider':
      return { id, type: 'divider', data: {} };
    default:
      return null;
  }
}

function sanitizeSize(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  if (Number.isFinite(parsed) && parsed >= 1 && parsed <= 12) {
    return parsed;
  }
  return fallback;
}

// Визуальный выбор размера таблицы (grid picker)
function showTableSizePicker() {
  return new Promise((resolve) => {
    const id = uuid();
    // Создаем модальное окно для выбора размера
    const overlay = document.createElement('div');
    overlay.className = 'table-size-picker-overlay';
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    `;

    const picker = document.createElement('div');
    picker.className = 'table-size-picker';
    picker.style.cssText = `
      background: var(--card);
      border-radius: 8px;
      padding: 20px;
      box-shadow: var(--shadow);
      border: 1px solid var(--border);
      max-width: 400px;
      color: var(--text);
    `;

    const title = document.createElement('h3');
    title.textContent = 'Выберите размер таблицы';
    title.style.cssText = 'margin: 0 0 16px 0; font-size: 18px; font-weight: 600; color: var(--text);';

    const grid = document.createElement('div');
    grid.className = 'table-size-grid';
    grid.style.cssText = `
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 4px;
      margin-bottom: 16px;
    `;

    let selectedRows = 3;
    let selectedCols = 3;

    // Создаем сетку 12x12
    for (let row = 0; row < 12; row++) {
      for (let col = 0; col < 12; col++) {
        const cell = document.createElement('div');
        cell.className = 'table-size-cell';
        cell.dataset.row = row + 1;
        cell.dataset.col = col + 1;
        cell.style.cssText = `
          width: 20px;
          height: 20px;
          border: 1px solid var(--border);
          background: var(--surface);
          cursor: pointer;
          transition: all 0.1s;
        `;

        cell.addEventListener('mouseenter', () => {
          // Подсвечиваем выбранную область
          const hoverRow = parseInt(cell.dataset.row, 10);
          const hoverCol = parseInt(cell.dataset.col, 10);
          
          grid.querySelectorAll('.table-size-cell').forEach((c) => {
            const cRow = parseInt(c.dataset.row, 10);
            const cCol = parseInt(c.dataset.col, 10);
            if (cRow <= hoverRow && cCol <= hoverCol) {
              c.style.background = 'var(--accent)';
              c.style.borderColor = 'var(--accent)';
            } else {
              c.style.background = 'var(--surface)';
              c.style.borderColor = 'var(--border)';
            }
          });

          selectedRows = hoverRow;
          selectedCols = hoverCol;
          sizeLabel.textContent = `${selectedRows} × ${selectedCols}`;
        });

        grid.appendChild(cell);
      }
    }

    // Подсвечиваем начальный размер 3x3
    grid.querySelectorAll('.table-size-cell').forEach((cell) => {
      const cRow = parseInt(cell.dataset.row, 10);
      const cCol = parseInt(cell.dataset.col, 10);
      if (cRow <= 3 && cCol <= 3) {
        cell.style.background = 'var(--accent)';
        cell.style.borderColor = 'var(--accent)';
      }
    });

    const sizeLabel = document.createElement('div');
    sizeLabel.textContent = '3 × 3';
    sizeLabel.style.cssText = `
      text-align: center;
      font-weight: 600;
      margin-bottom: 16px;
      font-size: 16px;
      color: var(--text);
    `;

    const buttons = document.createElement('div');
    buttons.style.cssText = 'display: flex; gap: 8px; justify-content: flex-end;';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Отмена';
    cancelBtn.style.cssText = `
      padding: 8px 16px;
      border: 1px solid var(--border);
      background: var(--surface);
      border-radius: 4px;
      cursor: pointer;
      color: var(--text);
    `;
    cancelBtn.addEventListener('click', () => {
      overlay.remove();
      resolve(null);
    });

    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = 'Создать';
    confirmBtn.style.cssText = `
      padding: 8px 16px;
      border: none;
      background: var(--accent);
      color: var(--on-accent);
      border-radius: 4px;
      cursor: pointer;
    `;
    confirmBtn.addEventListener('click', () => {
      const tableRows = Array.from({ length: selectedRows }, () => Array(selectedCols).fill(''));
      overlay.remove();
      document.removeEventListener('keydown', escapeHandler);
      resolve({ id: id, type: 'table', data: { rows: tableRows } });
    });

    buttons.appendChild(cancelBtn);
    buttons.appendChild(confirmBtn);

    picker.appendChild(title);
    picker.appendChild(grid);
    picker.appendChild(sizeLabel);
    picker.appendChild(buttons);
    overlay.appendChild(picker);
    document.body.appendChild(overlay);

    // Обработчик Escape (объявляем до использования)
    const escapeHandler = (e) => {
      if (e.key === 'Escape') {
        overlay.remove();
        document.removeEventListener('keydown', escapeHandler);
        resolve(null);
      }
    };

    // Устанавливаем обработчик клика на ячейки после создания всех ячеек
    grid.querySelectorAll('.table-size-cell').forEach((cell) => {
      cell.addEventListener('click', () => {
        const hoverRow = parseInt(cell.dataset.row, 10);
        const hoverCol = parseInt(cell.dataset.col, 10);
        const tableRows = Array.from({ length: hoverRow }, () => Array(hoverCol).fill(''));
        overlay.remove();
        document.removeEventListener('keydown', escapeHandler);
        resolve({ id: id, type: 'table', data: { rows: tableRows } });
      });
    });

    document.addEventListener('keydown', escapeHandler);

    // Закрытие по клику на overlay
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        overlay.remove();
        document.removeEventListener('keydown', escapeHandler);
        resolve(null);
      }
    });
  });
}
