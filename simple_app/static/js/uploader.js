import { uuid } from './utils.js';

const SUCCESS_HIDE_DELAY = 3200;
const ERROR_HIDE_DELAY = 6200;

export function initUploader({
  attachBtn,
  fileInput,
  dropOverlay,
  statusEl,
  ensureNote,
  onBlocksReady,
  getDragState,
}) {
  if (!fileInput || typeof ensureNote !== 'function' || typeof onBlocksReady !== 'function') {
    return null;
  }

  const uploads = new Map();
  let dragDepth = 0;

  attachBtn?.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (event) => {
    const files = Array.from(event.target.files || []);
    queueFiles(files);
    fileInput.value = '';
  });

  // Проверяем, не происходит ли перетаскивание блока
  function isBlockDrag(event) {
    // Если перетаскивается элемент с классом note-block-shell или его дочерние элементы
    const target = event.target;
    if (target?.closest?.('.note-block-shell')) {
      return true;
    }
    // Проверяем, есть ли активное перетаскивание блока через dragState
    if (typeof getDragState === 'function') {
      const dragState = getDragState();
      if (dragState && dragState.activeId) {
        return true;
      }
    }
    return false;
  }

  window.addEventListener(
    'dragover',
    (event) => {
      if (!hasFiles(event) || isBlockDrag(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
    },
    { passive: false },
  );

  window.addEventListener(
    'dragenter',
    (event) => {
      if (!hasFiles(event) || isBlockDrag(event)) return;
      dragDepth += 1;
      showOverlay();
    },
    { passive: true },
  );

  window.addEventListener(
    'dragleave',
    (event) => {
      if (!hasFiles(event) || isBlockDrag(event)) return;
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) hideOverlay();
    },
    { passive: true },
  );

  window.addEventListener(
    'drop',
    (event) => {
      if (!hasFiles(event) || isBlockDrag(event)) return;
      event.preventDefault();
      dragDepth = 0;
      hideOverlay();
      const files = Array.from(event.dataTransfer?.files || []);
      queueFiles(files);
    },
    { passive: false },
  );

  document.addEventListener('paste', (event) => {
    const files = Array.from(event.clipboardData?.files || []);
    if (!files.length) return;
    event.preventDefault();
    queueFiles(files);
  });

  function hasFiles(event) {
    const types = Array.from(event.dataTransfer?.types || []);
    // Проверяем, что это файлы, а не перетаскивание блока
    // Если есть text/plain и это может быть перетаскивание блока, игнорируем
    if (types.includes('text/plain') && !types.includes('Files')) {
      return false; // Это может быть перетаскивание блока или текста
    }
    return types.includes('Files');
  }

  function showOverlay() {
    if (!dropOverlay) return;
    dropOverlay.hidden = false;
    dropOverlay.classList.add('is-visible');
    dropOverlay.setAttribute('aria-hidden', 'false');
  }

  function hideOverlay() {
    if (!dropOverlay) return;
    dropOverlay.hidden = true;
    dropOverlay.classList.remove('is-visible');
    dropOverlay.setAttribute('aria-hidden', 'true');
  }

  async function queueFiles(files) {
    const filtered = files.filter((file) => file && file.size);
    if (!filtered.length) return;
    let noteId = null;
    try {
      noteId = await ensureNote();
    } catch (error) {
      displayGlobalError(error);
      return;
    }
    for (const file of filtered) {
      await uploadSingle(noteId, file);
    }
  }

  function displayGlobalError(error) {
    if (!statusEl) {
      console.error(error);
      return;
    }
    const id = uuid();
    uploads.set(id, {
      id,
      name: 'Ошибка загрузки',
      state: 'error',
      progress: 0,
      message: error?.message || 'Не удалось создать заметку для загрузки',
    });
    renderStatus();
    window.setTimeout(() => {
      uploads.delete(id);
      renderStatus();
    }, ERROR_HIDE_DELAY);
  }

  async function uploadSingle(noteId, file) {
    const uploadId = uuid();
    const record = {
      id: uploadId,
      name: file.name || 'Файл',
      size: file.size,
      state: 'uploading',
      progress: 0,
      message: '',
    };
    uploads.set(uploadId, record);
    renderStatus();

    try {
      const blocks = await sendFile(noteId, file, (value) => {
        record.progress = value;
        renderStatus();
      });
      record.state = 'success';
      record.progress = 1;
      renderStatus();
      if (Array.isArray(blocks) && blocks.length) {
        onBlocksReady(blocks);
      }
      window.setTimeout(() => {
        uploads.delete(uploadId);
        renderStatus();
      }, SUCCESS_HIDE_DELAY);
    } catch (error) {
      record.state = 'error';
      record.message = error?.message || 'Ошибка загрузки';
      renderStatus();
      window.setTimeout(() => {
        uploads.delete(uploadId);
        renderStatus();
      }, ERROR_HIDE_DELAY);
    }
  }

  function sendFile(noteId, file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const url = new URL('/api/upload', window.location.origin);
      if (noteId) {
        url.searchParams.set('noteId', noteId);
      }
      xhr.open('POST', url.toString());
      xhr.responseType = 'json';
      xhr.upload.addEventListener(
        'progress',
        (event) => {
          if (!event.lengthComputable) return;
          onProgress(event.loaded / event.total);
        },
        false,
      );

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const payload = xhr.response ?? {};
          resolve(payload.blocks || []);
        } else {
          const detail =
            xhr.response?.detail ||
            xhr.statusText ||
            (typeof xhr.response === 'string' ? xhr.response : 'Upload failed');
          reject(new Error(detail));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Сеть недоступна'));
      });

      const form = new FormData();
      form.append('files', file, file.name || 'upload');
      xhr.send(form);
    });
  }

  function renderStatus() {
    if (!statusEl) return;
    if (!uploads.size) {
      statusEl.innerHTML = '';
      statusEl.hidden = true;
      return;
    }
    statusEl.hidden = false;
    statusEl.innerHTML = '';
    uploads.forEach((upload) => {
      const item = document.createElement('div');
      item.className = `upload-progress__item upload-progress__item--${upload.state}`;

      const title = document.createElement('div');
      title.className = 'upload-progress__name';
      title.textContent = upload.name;

      const bar = document.createElement('div');
      bar.className = 'upload-progress__bar';
      const fill = document.createElement('div');
      fill.className = 'upload-progress__fill';
      fill.style.width = `${Math.round((upload.progress || 0) * 100)}%`;
      bar.appendChild(fill);

      const status = document.createElement('div');
      status.className = 'upload-progress__status';
      status.textContent = getStatusLabel(upload);

      item.appendChild(title);
      item.appendChild(bar);
      item.appendChild(status);
      if (upload.message && upload.state === 'error') {
        const hint = document.createElement('div');
        hint.className = 'upload-progress__hint';
        hint.textContent = upload.message;
        item.appendChild(hint);
      }
      statusEl.appendChild(item);
    });
  }

  function getStatusLabel(upload) {
    switch (upload.state) {
      case 'uploading':
        return `${Math.round((upload.progress || 0) * 100)}%`;
      case 'success':
        return 'Готово';
      case 'error':
        return 'Ошибка';
      default:
        return '';
    }
  }

  return {
    queueFiles,
  };
}
