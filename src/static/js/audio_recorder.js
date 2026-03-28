let audioToastHost = null;
let audioToastTimer = null;
let lastAudioToastMessage = '';
let lastAudioToastAt = 0;

function showAudioToast(message, type = 'error') {
  if (!message) return;
  const now = Date.now();
  if (message === lastAudioToastMessage && now - lastAudioToastAt < 1800) {
    return;
  }
  lastAudioToastMessage = message;
  lastAudioToastAt = now;

  if (!audioToastHost) {
    audioToastHost = document.createElement('div');
    audioToastHost.setAttribute('role', 'status');
    audioToastHost.setAttribute('aria-live', 'polite');
    audioToastHost.className = 'audio-toast-host';
    document.body.appendChild(audioToastHost);
  }

  const toast = document.createElement('div');
  toast.className = `audio-toast audio-toast--${type}`;
  toast.textContent = message;
  audioToastHost.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('audio-toast--visible');
  });

  if (audioToastTimer) {
    window.clearTimeout(audioToastTimer);
  }
  audioToastTimer = window.setTimeout(() => {
    toast.classList.remove('audio-toast--visible');
    window.setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
      if (audioToastHost && !audioToastHost.hasChildNodes()) {
        audioToastHost.remove();
        audioToastHost = null;
      }
    }, 180);
  }, 3200);
}

function setAudioError(button, message) {
  button.title = message;
  showAudioToast(message, 'error');
}

export function initAudioRecorder({ button, uploader, onReady }) {
  if (!button || !uploader) {
    return null;
  }

  const hasGetUserMedia = Boolean(navigator.mediaDevices?.getUserMedia);
  const hasMediaRecorder = typeof window.MediaRecorder !== 'undefined';
  const hasAudioContext = typeof window.AudioContext !== 'undefined' || typeof window.webkitAudioContext !== 'undefined';
  if (!hasGetUserMedia || (!hasMediaRecorder && !hasAudioContext)) {
    button.dataset.voiceStatus = 'error';
    button.classList.add('fab--error');
    setAudioError(button, 'Запись недоступна в текущем окружении');
    return null;
  }

  let mediaRecorder = null;
  let mediaChunks = [];
  let activeStream = null;
  let state = 'idle';
  let stopRequested = false;
  let activeMimeType = 'audio/webm';
  let recordingStartedAt = 0;

  // Desktop WebView can stop MediaRecorder prematurely. Use PCM/WAV fallback there.
  let usePcmMode = false;
  let pcmContext = null;
  let pcmSource = null;
  let pcmProcessor = null;
  let pcmSilentGain = null;
  let pcmChunks = [];

  const defaultIcon = button.textContent || '🎙';
  const MIN_STOP_DELAY_MS = 250;
  const MIN_BLOB_BYTES = 128;
  const isDesktop = Boolean(window.__DESKTOP_MODE || window.__TAURI__);

  // Preserve original stable web behavior.
  if (!isDesktop) {
    return initBrowserRecorder({ button, uploader, onReady });
  }

  button.addEventListener('click', async () => {
    if (state === 'uploading' || state === 'processing') return;
    if (state === 'recording') {
      await stopRecording();
    } else {
      await startRecording();
    }
  });

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      activeStream = stream;
      mediaChunks = [];
      pcmChunks = [];
      stopRequested = false;
      usePcmMode = false;

      activeStream.getAudioTracks().forEach((track) => {
        track.addEventListener('ended', () => {
          if (state === 'recording' && !stopRequested) {
            setAudioError(button, 'Запись прервалась. Проверь доступ к микрофону.');
            failAndReset();
          }
        });
      });

      if (isDesktop && hasAudioContext) {
        const started = await startPcmRecorder(stream);
        if (started) {
          recordingStartedAt = Date.now();
          applyStatus('recording');
          return;
        }
      }

      if (!hasMediaRecorder) {
        throw new Error('MediaRecorder is unavailable');
      }

      const mimeType = getSupportedMimeType();
      mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      activeMimeType = mediaRecorder.mimeType || mimeType || 'audio/webm';
      mediaChunks = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size) {
          mediaChunks.push(event.data);
        }
      };

      mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error', event);
        setAudioError(button, 'Ошибка записи аудио.');
        failAndReset();
      };

      mediaRecorder.onstop = () => {
        handleMediaStop(stopRequested);
      };

      // timeslice helps Safari/WKWebView deliver chunks reliably.
      mediaRecorder.start(250);
      recordingStartedAt = Date.now();
      applyStatus('recording');
    } catch (error) {
      const errName = error?.name || 'Error';
      if (errName === 'NotAllowedError') {
        setAudioError(button, 'Нет доступа к микрофону. Разреши доступ в настройках macOS.');
      } else if (errName === 'NotFoundError') {
        setAudioError(button, 'Микрофон не найден.');
      } else {
        setAudioError(button, 'Ошибка доступа к микрофону.');
      }
      console.error('Microphone access denied', error);
      failAndReset();
    }
  }

  async function stopRecording() {
    const elapsed = recordingStartedAt ? Date.now() - recordingStartedAt : 0;
    if (elapsed < MIN_STOP_DELAY_MS) {
      return;
    }
    stopRequested = true;
    applyStatus('uploading');

    if (usePcmMode) {
      const blob = await stopPcmRecorder();
      await finalizeRecording(blob, 'audio/wav');
      return;
    }

    if (!mediaRecorder || mediaRecorder.state !== 'recording') {
      setAudioError(button, 'Не удалось остановить запись. Попробуй снова.');
      failAndReset();
      return;
    }

    try {
      mediaRecorder.requestData();
    } catch (_) {
      // Some engines don't support requestData in current state.
    }
    mediaRecorder.stop();
  }

  async function handleMediaStop(userInitiated) {
    if (!userInitiated) {
      setAudioError(button, 'Запись прервалась. Попробуй снова.');
      failAndReset();
      return;
    }

    if (!mediaChunks.length) {
      setAudioError(button, 'Аудио не записалось. Попробуй ещё раз.');
      failAndReset();
      return;
    }

    const recordedMime = activeMimeType || mediaRecorder?.mimeType || 'audio/webm';
    const blob = new Blob(mediaChunks, { type: recordedMime });
    await finalizeRecording(blob, recordedMime);
  }

  async function finalizeRecording(blob, mimeType) {
    try {
      if (!blob || !blob.size || blob.size < MIN_BLOB_BYTES) {
        setAudioError(button, 'Слишком короткая запись.');
        failAndReset();
        return;
      }

      const fileName = `recording-${Date.now()}${extensionForMime(mimeType)}`;
      const file = new File([blob], fileName, { type: blob.type || mimeType || 'audio/webm' });

      applyStatus('uploading');
      await uploader.queueFiles([file]);

      applyStatus('processing');
      try {
        await transcribe(file);
      } catch (transcribeError) {
        // Transcription is optional; do not fail saved audio.
        console.warn('Voice transcription failed, continuing without transcript', transcribeError);
        showAudioToast('Аудио сохранено, но распознавание сейчас недоступно.', 'warning');
      }

      if (typeof onReady === 'function') onReady();
      resetState();
    } catch (error) {
      console.error('Failed to upload recording', error);
      setAudioError(button, 'Ошибка загрузки аудио. Проверь сеть и попробуй снова.');
      failAndReset();
    }
  }

  async function startPcmRecorder(stream) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return false;
    try {
      const context = new Ctx();
      await context.resume();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const silentGain = context.createGain();
      silentGain.gain.value = 0;

      pcmChunks = [];
      processor.onaudioprocess = (event) => {
        if (state !== 'recording') return;
        const input = event.inputBuffer.getChannelData(0);
        pcmChunks.push(new Float32Array(input));
      };

      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(context.destination);

      pcmContext = context;
      pcmSource = source;
      pcmProcessor = processor;
      pcmSilentGain = silentGain;
      usePcmMode = true;
      activeMimeType = 'audio/wav';
      return true;
    } catch (error) {
      console.warn('PCM recorder init failed, fallback to MediaRecorder', error);
      cleanupPcmNodes();
      return false;
    }
  }

  async function stopPcmRecorder() {
    try {
      const ctx = pcmContext;
      const sampleRate = ctx?.sampleRate || 44100;
      const samples = mergePcmChunks(pcmChunks);
      cleanupPcmNodes();
      if (!samples.length) return null;
      const wavBytes = encodeWav(samples, sampleRate);
      return new Blob([wavBytes], { type: 'audio/wav' });
    } catch (error) {
      console.error('Failed to finalize PCM recording', error);
      cleanupPcmNodes();
      return null;
    }
  }

  function cleanupPcmNodes() {
    try {
      if (pcmProcessor) {
        pcmProcessor.onaudioprocess = null;
        pcmProcessor.disconnect();
      }
      if (pcmSource) pcmSource.disconnect();
      if (pcmSilentGain) pcmSilentGain.disconnect();
      if (pcmContext) {
        pcmContext.close().catch(() => {});
      }
    } catch (_) {
      // Ignore cleanup errors.
    } finally {
      pcmProcessor = null;
      pcmSource = null;
      pcmSilentGain = null;
      pcmContext = null;
      pcmChunks = [];
      usePcmMode = false;
    }
  }

  async function transcribe(file) {
    const form = new FormData();
    form.append('file', file, file.name || 'recording.webm');
    const response = await fetch('/api/transcribe', {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || 'Транскрибация недоступна');
    }
    return response.text();
  }

  function applyStatus(nextState) {
    state = nextState;
    button.dataset.voiceStatus = nextState;
    button.classList.remove('fab--recording', 'fab--processing', 'fab--uploading', 'fab--error');
    button.removeAttribute('aria-pressed');

    switch (nextState) {
      case 'recording':
        button.classList.add('fab--recording');
        button.setAttribute('aria-pressed', 'true');
        button.textContent = '●';
        button.title = 'Запись...';
        break;
      case 'uploading':
        button.classList.add('fab--uploading');
        button.textContent = '⇪';
        button.title = 'Загрузка аудио...';
        break;
      case 'processing':
        button.classList.add('fab--processing');
        button.textContent = '…';
        button.title = 'Обработка...';
        break;
      case 'error':
        button.classList.add('fab--error');
        button.textContent = '!';
        button.title = button.title || 'Ошибка записи';
        break;
      default:
        button.textContent = defaultIcon;
        button.title = 'Добавить голосовую заметку';
        break;
    }
  }

  function failAndReset() {
    applyStatus('error');
    window.setTimeout(() => {
      resetState();
    }, 1200);
  }

  function resetState() {
    if (activeStream) {
      activeStream.getTracks().forEach((track) => track.stop());
    }
    activeStream = null;
    mediaRecorder = null;
    mediaChunks = [];
    stopRequested = false;
    recordingStartedAt = 0;
    cleanupPcmNodes();
    applyStatus('idle');
  }

  applyStatus('idle');
}

function getSupportedMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4;codecs=mp4a.40.2',
    'audio/mp4',
    'audio/x-m4a',
    'audio/m4a',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

function extensionForMime(mimeType) {
  const m = (mimeType || '').toLowerCase();
  if (m.includes('wav')) return '.wav';
  if (m.includes('mp4') || m.includes('m4a')) return '.m4a';
  if (m.includes('ogg')) return '.ogg';
  return '.webm';
}

function mergePcmChunks(chunks) {
  if (!Array.isArray(chunks) || !chunks.length) {
    return new Float32Array(0);
  }
  let totalLength = 0;
  chunks.forEach((chunk) => {
    totalLength += chunk.length;
  });
  const result = new Float32Array(totalLength);
  let offset = 0;
  chunks.forEach((chunk) => {
    result.set(chunk, offset);
    offset += chunk.length;
  });
  return result;
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  writeAscii(view, 0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(view, 8, 'WAVE');
  writeAscii(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(view, 36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return buffer;
}

function writeAscii(view, offset, value) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i));
  }
}

function initBrowserRecorder({ button, uploader, onReady }) {
  let mediaRecorder = null;
  let chunks = [];
  let activeStream = null;
  let state = 'idle';
  const defaultIcon = button.textContent || '🎙';

  button.addEventListener('click', async () => {
    if (state === 'recording') {
      stopRecording();
    } else {
      await startRecording();
    }
  });

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      activeStream = stream;
      chunks = [];
      const mimeType = getSupportedMimeType();
      mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size) {
          chunks.push(event.data);
        }
      };
      mediaRecorder.onstop = handleStop;
      mediaRecorder.start();
      state = 'recording';
      button.classList.add('fab--recording');
      button.setAttribute('aria-pressed', 'true');
      button.textContent = '●';
    } catch (error) {
      console.error('Microphone access denied', error);
      const errName = error?.name || 'Error';
      if (errName === 'NotAllowedError') {
        setAudioError(button, 'Нет доступа к микрофону. Разрешите доступ в браузере.');
      } else if (errName === 'NotFoundError') {
        setAudioError(button, 'Микрофон не найден.');
      } else {
        setAudioError(button, 'Не удалось начать запись.');
      }
      resetState();
    }
  }

  function stopRecording() {
    if (!mediaRecorder) return;
    mediaRecorder.stop();
    state = 'processing';
    button.classList.remove('fab--recording');
    button.classList.add('fab--processing');
    button.textContent = '…';
  }

  async function handleStop() {
    try {
      if (!chunks.length) {
        setAudioError(button, 'Аудио не записалось. Попробуйте ещё раз.');
        resetState();
        return;
      }
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      const fileName = `recording-${Date.now()}.webm`;
      const file = new File([blob], fileName, { type: blob.type });
      await uploader.queueFiles([file]);
      if (typeof onReady === 'function') onReady();
    } catch (error) {
      console.error('Failed to upload recording', error);
      setAudioError(button, 'Ошибка загрузки аудио. Проверьте сеть и попробуйте снова.');
    } finally {
      resetState();
    }
  }

  function resetState() {
    if (activeStream) {
      activeStream.getTracks().forEach((track) => track.stop());
    }
    activeStream = null;
    mediaRecorder = null;
    chunks = [];
    state = 'idle';
    button.classList.remove('fab--recording');
    button.classList.remove('fab--processing');
    button.removeAttribute('aria-pressed');
    button.textContent = defaultIcon;
  }

  return {
    stop: resetState,
  };
}
