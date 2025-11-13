const waveformCache = new Map();

export function initAudioPlayers(container, onBlockUpdate) {
  if (!container) return;
  const blocks = container.querySelectorAll('.audio-block');
  blocks.forEach((block) => {
    if (block.dataset.audioReady === 'true') return;
    block.dataset.audioReady = 'true';
    setupAudioBlock(block, onBlockUpdate);
  });
}

function setupAudioBlock(block, onBlockUpdate) {
  const audioEl = block.querySelector('audio');
  if (!audioEl) return;

  const playBtn = block.querySelector('[data-action="play"]');
  const toggleBtn = block.querySelector('[data-action="toggle-view"]');
  const rewindBtn = block.querySelector('[data-action="rewind-10"]');
  const forwardBtn = block.querySelector('[data-action="ffwd-10"]');
  const downloadBtn = block.querySelector('[data-action="download"]');
  const timeline = block.querySelector('.audio-timeline');
  const progressEl = block.querySelector('.audio-progress');
  const currentLabel = block.querySelector('.audio-time__current');
  const durationLabel = block.querySelector('.audio-time__duration');
  const expanded = block.querySelector('.audio-expanded');
  const canvas = block.querySelector('.audio-wave');
  const waveformUrl = block.dataset.waveform;
  const blockId = block.dataset.blockId;

  let durationFromMetadata = false;

  if (playBtn) {
    playBtn.addEventListener('click', () => {
      if (audioEl.paused) {
        audioEl.play();
        playBtn.textContent = '⏸';
      } else {
        audioEl.pause();
        playBtn.textContent = '▶';
      }
    });
  }

  audioEl.addEventListener('ended', () => {
    audioEl.currentTime = 0;
    playBtn.textContent = '▶';
  });

  audioEl.addEventListener('timeupdate', () => {
    updateProgress();
  });

  audioEl.addEventListener('loadedmetadata', () => {
    if (!Number.isFinite(audioEl.duration)) return;
    durationLabel.textContent = formatTime(audioEl.duration);
    if (!block.dataset.duration && typeof onBlockUpdate === 'function' && blockId) {
      onBlockUpdate(blockId, { duration: Number(audioEl.duration.toFixed(2)) });
    }
    durationFromMetadata = true;
  });

  if (toggleBtn && expanded) {
    toggleBtn.addEventListener('click', () => {
      const nextView = block.dataset.view === 'expanded' ? 'mini' : 'expanded';
      block.dataset.view = nextView;
      expanded.hidden = nextView !== 'expanded';
      toggleBtn.textContent = nextView === 'expanded' ? '▾' : '▤';
      if (typeof onBlockUpdate === 'function' && blockId) {
        onBlockUpdate(blockId, { view: nextView });
      }
    });
  }

  rewindBtn?.addEventListener('click', () => {
    audioEl.currentTime = Math.max(0, audioEl.currentTime - 10);
  });

  forwardBtn?.addEventListener('click', () => {
    audioEl.currentTime = Math.min(audioEl.duration || audioEl.currentTime + 10, audioEl.currentTime + 10);
  });

  if (downloadBtn && audioEl.src) {
    downloadBtn.addEventListener('click', () => {
      window.open(audioEl.src, '_blank');
    });
  }

  if (timeline) {
    timeline.addEventListener('click', (event) => {
      const rect = timeline.getBoundingClientRect();
      const ratio = (event.clientX - rect.left) / rect.width;
      if (Number.isFinite(audioEl.duration)) {
        audioEl.currentTime = Math.max(0, Math.min(audioEl.duration * ratio, audioEl.duration));
      }
    });
  }

  function updateProgress() {
    if (currentLabel) currentLabel.textContent = formatTime(audioEl.currentTime);
    const percent = audioEl.duration ? (audioEl.currentTime / audioEl.duration) * 100 : 0;
    if (progressEl) progressEl.style.width = `${percent}%`;
  }

  if (waveformUrl && canvas) {
    fetchWaveform(waveformUrl)
      .then((values) => drawWave(canvas, values))
      .catch(() => drawWave(canvas, _defaultWaveform()));
  } else if (canvas) {
    drawWave(canvas, _defaultWaveform());
  }

  function drawWave(canvasEl, values) {
    const ctx = canvasEl.getContext('2d');
    if (!ctx) return;
    const width = canvasEl.clientWidth || timeline?.clientWidth || 200;
    const height = canvasEl.clientHeight || 40;
    canvasEl.width = width;
    canvasEl.height = height;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = 'rgba(255,255,255,0.7)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    const step = width / values.length;
    values.forEach((value, index) => {
      const amp = Math.max(0.05, value);
      const x = index * step + step / 2;
      const y = (height / 2) * (1 - amp);
      const y2 = height - y;
      ctx.moveTo(x, y);
      ctx.lineTo(x, y2);
    });
    ctx.stroke();
  }

  function fetchWaveform(url) {
    if (waveformCache.has(url)) return Promise.resolve(waveformCache.get(url));
    return fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error('waveform');
        return res.json();
      })
      .then((values) => {
        waveformCache.set(url, values);
        return values;
      });
  }
}

function formatTime(value) {
  if (!Number.isFinite(value)) return '0:00';
  const totalSeconds = Math.max(0, Math.floor(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function _defaultWaveform(points = 64) {
  return Array.from({ length: points }, () => 0.2);
}
