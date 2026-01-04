export function initAudioRecorder({ button, uploader, onReady }) {
  if (!button || !uploader || !navigator.mediaDevices?.getUserMedia) {
    return null;
  }

  let mediaRecorder = null;
  let chunks = [];
  let activeStream = null;
  let state = 'idle';

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
    } catch (error) {
      console.error('Microphone access denied', error);
      resetState();
    }
  }

  function stopRecording() {
    if (!mediaRecorder) return;
    mediaRecorder.stop();
    state = 'processing';
    button.classList.remove('fab--recording');
    button.classList.add('fab--processing');
  }

  async function handleStop() {
    try {
      if (!chunks.length) {
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
  }
}

function getSupportedMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}
