export function initAudioPlayers(container, onBlockUpdate) {
  if (!container) return;
  const blocks = container.querySelectorAll('.audio-block');
  console.log('Audio player: initAudioPlayers called', { blocksCount: blocks.length, container });
  blocks.forEach((block) => {
    const audioEl = block.querySelector('audio');
    if (!audioEl) return;
    
    // OVC: audio - проверяем, нужно ли переинициализировать блок
    const savedSrc = audioEl.dataset.savedSrc;
    const currentSrc = audioEl.src;
    const needsReinit = !block.dataset.audioReady || savedSrc !== currentSrc;
    
    if (block.dataset.audioReady === 'true' && !needsReinit) {
      // Блок уже инициализирован и src не изменился - восстанавливаем состояние
      const wasPlaying = audioEl.dataset.wasPlaying === 'true';
      const savedTime = parseFloat(audioEl.dataset.savedTime || '0');
      
      if (audioEl.readyState >= 2 && savedTime > 0) {
        audioEl.currentTime = savedTime;
        if (wasPlaying && audioEl.paused) {
          audioEl.play().catch(err => console.warn('Audio player: failed to resume', err));
        }
      }
      return;
    }
    
    // Инициализируем новый блок или переинициализируем, если src изменился
    block.dataset.audioReady = 'true';
    audioEl.dataset.savedSrc = currentSrc;
    
    // OVC: audio - если есть сохраненное состояние, восстанавливаем его после инициализации
    const wasPlaying = audioEl.dataset.wasPlaying === 'true';
    const savedTime = parseFloat(audioEl.dataset.savedTime || '0');
    
    setupAudioBlock(block, onBlockUpdate);
    
    // Восстанавливаем состояние после инициализации
    if (savedTime > 0) {
      const restoreState = () => {
        if (audioEl.readyState >= 2) {
          audioEl.currentTime = savedTime;
          if (wasPlaying && audioEl.paused) {
            audioEl.play().catch(err => console.warn('Audio player: failed to resume after reinit', err));
          }
        } else {
          // Ждем, пока аудио загрузится
          audioEl.addEventListener('canplay', () => {
            audioEl.currentTime = savedTime;
            if (wasPlaying && audioEl.paused) {
              audioEl.play().catch(err => console.warn('Audio player: failed to resume after reinit', err));
            }
          }, { once: true });
        }
      };
      
      // Пытаемся восстановить сразу, если возможно
      if (audioEl.readyState >= 2) {
        restoreState();
      } else {
        // Иначе ждем загрузки
        audioEl.addEventListener('loadedmetadata', restoreState, { once: true });
      }
    }
  });
}

function setupAudioBlock(block, onBlockUpdate) {
  const audioEl = block.querySelector('audio');
  if (!audioEl) {
    console.warn('Audio player: audio element not found in block', block);
    return;
  }

  const playBtn = block.querySelector('[data-action="play"]');
  if (!playBtn) {
    console.warn('Audio player: play button not found in block', block);
    return;
  }
  
  console.log('Audio player: setting up audio block', { 
    blockId: block.dataset.blockId, 
    src: audioEl.src,
    hasPlayBtn: !!playBtn 
  });
  const toggleBtn = block.querySelector('[data-action="toggle-view"]');
  const rewindBtn = block.querySelector('[data-action="rewind-10"]');
  const forwardBtn = block.querySelector('[data-action="ffwd-10"]');
  const downloadBtn = block.querySelector('[data-action="download"]');
  const timeline = block.querySelector('.audio-timeline');
  const progressEl = block.querySelector('.audio-progress');
  const currentLabel = block.querySelector('.audio-time__current');
  const durationLabel = block.querySelector('.audio-time__duration');
  const expanded = block.querySelector('.audio-expanded');
  const blockId = block.dataset.blockId;

  let durationFromMetadata = false;

  if (playBtn) {
    playBtn.addEventListener('click', async (e) => {
      // OVC: audio - предотвращаем всплытие события, чтобы не вызвать render()
      e.stopPropagation();
      e.preventDefault();
      
      if (audioEl.paused) {
        try {
          // OVC: audio - проверяем, что аудио готово к воспроизведению
          if (audioEl.readyState < 2) {
            console.warn('Audio player: not ready to play', { readyState: audioEl.readyState });
            // Ждем, пока аудио загрузится
            audioEl.addEventListener('canplay', async () => {
              try {
                await audioEl.play();
                playBtn.textContent = '⏸';
                console.log('Audio player: playback started after canplay', { src: audioEl.src });
              } catch (err) {
                console.error('Audio player: playback failed after canplay', { error: err, src: audioEl.src });
              }
            }, { once: true });
            return;
          }
          
          await audioEl.play();
        playBtn.textContent = '⏸';
          console.log('Audio player: playback started', { 
            src: audioEl.src, 
            readyState: audioEl.readyState,
            duration: audioEl.duration 
          });
        } catch (error) {
          console.error('Audio player: playback failed', { 
            error, 
            src: audioEl.src,
            errorCode: audioEl.error?.code,
            errorMessage: audioEl.error?.message,
            readyState: audioEl.readyState,
            networkState: audioEl.networkState
          });
          playBtn.textContent = '▶';
        }
      } else {
        audioEl.pause();
        playBtn.textContent = '▶';
        console.log('Audio player: playback paused');
      }
    });
  }
  
  // OVC: audio - отслеживаем события воспроизведения
  audioEl.addEventListener('playing', () => {
    console.log('Audio player: actually playing', { src: audioEl.src, currentTime: audioEl.currentTime });
  });
  
  audioEl.addEventListener('pause', () => {
    console.log('Audio player: paused', { src: audioEl.src, currentTime: audioEl.currentTime });
  });
  
  audioEl.addEventListener('waiting', () => {
    console.warn('Audio player: waiting for data', { src: audioEl.src });
  });
  
  audioEl.addEventListener('stalled', () => {
    console.warn('Audio player: stalled', { src: audioEl.src });
  });

  audioEl.addEventListener('ended', () => {
    audioEl.currentTime = 0;
    playBtn.textContent = '▶';
  });

  audioEl.addEventListener('timeupdate', () => {
    updateProgress();
    // OVC: audio - сохраняем текущее время воспроизведения для восстановления после рендера
    audioEl.dataset.savedTime = String(audioEl.currentTime);
    audioEl.dataset.wasPlaying = String(!audioEl.paused);
  });

  audioEl.addEventListener('loadedmetadata', () => {
    console.log('Audio player: metadata loaded', { 
      duration: audioEl.duration, 
      src: audioEl.src,
      readyState: audioEl.readyState 
    });
    if (!Number.isFinite(audioEl.duration)) return;
    durationLabel.textContent = formatTime(audioEl.duration);
    if (!block.dataset.duration && typeof onBlockUpdate === 'function' && blockId) {
      onBlockUpdate(blockId, { duration: Number(audioEl.duration.toFixed(2)) });
    }
    durationFromMetadata = true;
  });

  audioEl.addEventListener('error', (e) => {
    console.error('Audio player: error loading audio', { 
      error: e, 
      src: audioEl.src,
      errorCode: audioEl.error?.code,
      errorMessage: audioEl.error?.message,
      networkState: audioEl.networkState,
      readyState: audioEl.readyState
    });
  });

  audioEl.addEventListener('canplay', () => {
    console.log('Audio player: can play', { src: audioEl.src });
  });

  audioEl.addEventListener('loadstart', () => {
    console.log('Audio player: load started', { src: audioEl.src });
    // OVC: audio - если аудио перезагружается, но мы уже были в процессе воспроизведения, восстанавливаем
    const wasPlaying = audioEl.dataset.wasPlaying === 'true';
    const savedTime = parseFloat(audioEl.dataset.savedTime || '0');
    if (wasPlaying && savedTime > 0) {
      audioEl.addEventListener('canplay', () => {
        audioEl.currentTime = savedTime;
        audioEl.play().catch(err => console.warn('Audio player: failed to resume playback', err));
      }, { once: true });
    }
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

  // OVC: audio - перемотка по клику и перетаскиванию на timeline
  let isDragging = false;
  let dragStartX = 0;
  let wasPlayingBeforeSeek = false;
  let justFinishedDragging = false; // Флаг для предотвращения двойной перемотки
  const dragTarget = timeline;
  
  function seekToPosition(clientX, element, preservePlayback = false) {
    const rect = element.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    if (Number.isFinite(audioEl.duration) && audioEl.duration > 0) {
      const newTime = audioEl.duration * ratio;
      // OVC: audio - сохраняем состояние воспроизведения перед перемоткой
      if (preservePlayback) {
        wasPlayingBeforeSeek = !audioEl.paused;
      }
      audioEl.currentTime = Math.max(0, Math.min(newTime, audioEl.duration));
      updateProgress();
      // OVC: audio - если аудио играло и нужно сохранить воспроизведение, продолжаем после перемотки
      if (preservePlayback && wasPlayingBeforeSeek && audioEl.paused) {
        // Используем небольшую задержку, чтобы браузер успел обработать изменение currentTime
        setTimeout(() => {
          audioEl.play().catch(err => console.warn('Audio player: failed to resume after seek', err));
        }, 10);
      }
    }
  }
  
  // Обработчики для document (добавляются/удаляются динамически)
  let dragMoveHandler = null;
  let dragEndHandler = null;
  
  function handleDragStart(e) {
    e.preventDefault();
    e.stopPropagation();
    isDragging = true;
    dragStartX = e.clientX || (e.touches && e.touches[0]?.clientX) || 0;
    const target = e.currentTarget;
    // OVC: audio - при перетаскивании сохраняем состояние воспроизведения
    seekToPosition(dragStartX, target, true);
    // Добавляем класс для визуальной обратной связи
    if (timeline) timeline.classList.add('dragging');
    
    // Создаем и добавляем обработчики на document только когда начинается перетаскивание
    if (!dragMoveHandler) {
      dragMoveHandler = (e) => {
        if (!isDragging || !timeline) return;
        e.preventDefault();
        e.stopPropagation();
        const clientX = e.clientX || (e.touches && e.touches[0]?.clientX) || dragStartX;
        // OVC: audio - при перетаскивании не сохраняем воспроизведение на каждом движении, только в начале
        seekToPosition(clientX, timeline, false);
      };
      
      dragEndHandler = (e) => {
        if (!isDragging) return;
        e.preventDefault();
        e.stopPropagation();
        isDragging = false;
        justFinishedDragging = true; // Устанавливаем флаг, чтобы игнорировать следующий click
        // Убираем класс визуальной обратной связи
        if (timeline) timeline.classList.remove('dragging');
        // OVC: audio - восстанавливаем воспроизведение после перетаскивания, если оно было включено
        if (wasPlayingBeforeSeek && audioEl.paused) {
          setTimeout(() => {
            audioEl.play().catch(err => console.warn('Audio player: failed to resume after drag', err));
          }, 10);
        }
        wasPlayingBeforeSeek = false;
        // Удаляем обработчики с document
        document.removeEventListener('mousemove', dragMoveHandler);
        document.removeEventListener('touchmove', dragMoveHandler);
        document.removeEventListener('mouseup', dragEndHandler);
        document.removeEventListener('touchend', dragEndHandler);
        dragMoveHandler = null;
        dragEndHandler = null;
        // Сбрасываем флаг через небольшую задержку, чтобы click успел сработать (если будет)
        setTimeout(() => {
          justFinishedDragging = false;
        }, 100);
      };
      
      document.addEventListener('mousemove', dragMoveHandler);
      document.addEventListener('touchmove', dragMoveHandler, { passive: false });
      document.addEventListener('mouseup', dragEndHandler);
      document.addEventListener('touchend', dragEndHandler);
    }
  }

  if (timeline) {
    // Клик на timeline для быстрой перемотки
    timeline.addEventListener('click', (event) => {
      // OVC: audio - предотвращаем всплытие события, чтобы не вызвать render()
      event.stopPropagation();
      event.preventDefault();
      // OVC: audio - если было перетаскивание, игнорируем клик (он сработает после mouseup)
      if (isDragging || justFinishedDragging) {
        return;
      }
      // OVC: audio - при клике сохраняем состояние воспроизведения
      seekToPosition(event.clientX, timeline, true);
    });
    
    // Перетаскивание на timeline
    timeline.addEventListener('mousedown', handleDragStart);
    timeline.addEventListener('touchstart', handleDragStart, { passive: false });
  }

  function updateProgress() {
    if (currentLabel) currentLabel.textContent = formatTime(audioEl.currentTime);
    const percent = audioEl.duration ? (audioEl.currentTime / audioEl.duration) * 100 : 0;
    if (progressEl) progressEl.style.width = `${percent}%`;
    // OVC: audio - убрали waveform для упрощения и производительности
  }
}

function formatTime(value) {
  if (!Number.isFinite(value)) return '0:00';
  const totalSeconds = Math.max(0, Math.floor(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}
