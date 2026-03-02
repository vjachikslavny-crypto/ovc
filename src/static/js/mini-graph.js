// mini-graph.js - Мини-граф связей в боковой панели

let miniGraphData = null;
let miniGraphSvg = null;
let miniGraphSimulation = null;
let currentNoteId = null;
let miniGraphNodeSelection = null;
let controlsInitialized = false;
let isInitializing = false;
let initTimeout = null;
let retryCount = 0;
const MAX_RETRIES = 5;
const INIT_SAFETY_MS = 8000;

// Функция для сброса состояния
function resetMiniGraph() {
  console.log('[MiniGraph] Resetting state...');
  miniGraphData = null;
  if (miniGraphSimulation) {
    miniGraphSimulation.stop();
  }
  miniGraphSimulation = null;
  miniGraphNodeSelection = null;
  controlsInitialized = false;
  
  // Очищаем SVG
  if (miniGraphSvg) {
    miniGraphSvg.selectAll('*').remove();
  }
}

// Инициализация мини-графа с debounce
export function initMiniGraph(options = {}) {
  const { force = false } = options;
  
  // При force-режиме сбрасываем блокировки и кеш
  if (force) {
    console.log('[MiniGraph] Force re-init requested');
    isInitializing = false;
    currentNoteId = null;
    miniGraphData = null;
  }
  
  // Предотвращаем множественные вызовы
  if (isInitializing) {
    console.log('[MiniGraph] Already initializing, skipping...');
    return;
  }
  
  // Очищаем предыдущий таймаут
  if (initTimeout) {
    clearTimeout(initTimeout);
  }
  
  // Debounce на 50ms
  initTimeout = setTimeout(() => {
    doInitMiniGraph();
  }, 50);
}

function doInitMiniGraph() {
  console.log('[MiniGraph] doInitMiniGraph called, isInitializing:', isInitializing);
  
  if (isInitializing) {
    console.log('[MiniGraph] Already initializing in doInit, aborting');
    return;
  }
  
  isInitializing = true;
  
  // Safety timeout: reset flag if initialization hangs
  setTimeout(() => {
    if (isInitializing) {
      console.warn('[MiniGraph] Safety timeout: resetting isInitializing');
      isInitializing = false;
    }
  }, INIT_SAFETY_MS);
  
  // Сбрасываем предыдущее состояние
  resetMiniGraph();
  
  // Проверяем наличие d3
  if (typeof d3 === 'undefined') {
    console.error('[MiniGraph] d3 is not loaded!');
    isInitializing = false;
    setTimeout(initMiniGraph, 100);
    return;
  }
  
  const editor = document.querySelector('.editor');
  let newNoteId = editor?.dataset?.noteId;
  
  // Fallback: извлекаем ID из URL если атрибут пуст
  if (!newNoteId) {
    const urlMatch = window.location.pathname.match(/\/notes\/([a-f0-9-]+)/);
    if (urlMatch) {
      newNoteId = urlMatch[1];
      console.log('[MiniGraph] Got note ID from URL:', newNoteId);
    }
  }
  
  console.log('[MiniGraph] Note ID:', newNoteId, '(previous:', currentNoteId, ')');
  
  if (!newNoteId) {
    console.log('[MiniGraph] No note ID found, retry count:', retryCount);
    isInitializing = false;
    
    // Retry через 200ms если DOM еще не готов (максимум 5 раз)
    if (retryCount < MAX_RETRIES) {
      retryCount++;
      setTimeout(() => {
        console.log('[MiniGraph] Retrying initialization... (attempt', retryCount, ')');
        initMiniGraph();
      }, 200);
    } else {
      console.error('[MiniGraph] Max retries reached, giving up');
      showEmptyState('Не удалось загрузить заметку');
      retryCount = 0;
    }
    return;
  }
  
  // Сбрасываем счетчик после успешного получения ID
  retryCount = 0;
  
  // Если это та же заметка, не перезагружаем
  if (currentNoteId === newNoteId && miniGraphData) {
    console.log('[MiniGraph] Same note, skipping reload');
    isInitializing = false;
    return;
  }
  
  currentNoteId = newNoteId;

  miniGraphSvg = d3.select('#mini-graph-svg');
  console.log('[MiniGraph] SVG element:', miniGraphSvg.node());
  
  // Показываем индикатор загрузки
  showEmptyState('Граф загружается...');
  
  // Загружаем данные графа (контролы инициализируются внутри после загрузки)
  loadGraphData();
}

// Загрузка данных графа
async function loadGraphData() {
  try {
    const response = await fetch('/api/graph');
    const data = await response.json();
    
    console.log('[MiniGraph] Raw API response:', data);
    console.log('[MiniGraph] Nodes:', data.nodes?.length || 0);
    console.log('[MiniGraph] Edges:', data.edges?.length || 0);
    
    // API возвращает edges, конвертируем в links для совместимости с d3
    if (!data.nodes) {
      data.nodes = [];
    }
    if (!data.edges) {
      data.edges = [];
    }
    
    // Конвертируем edges в links
    data.links = data.edges;
    
    if (data.links && data.links.length > 0) {
      console.log('[MiniGraph] First link:', data.links[0]);
    }
    
    // Проверяем, есть ли текущая заметка в графе
    const currentNode = data.nodes.find(n => n.id === currentNoteId);
    
    // Если текущей заметки нет в графе, добавляем её
    if (!currentNode) {
      console.log('[MiniGraph] Current note not in graph, adding it');
      const titleEl = document.getElementById('note-title');
      data.nodes.push({
        id: currentNoteId,
        title: titleEl?.textContent || 'Новая заметка',
        size: 1,
        color: null
      });
    }
    
    // Проверяем связи с текущей заметкой
    const relatedLinks = data.links.filter(l => {
      return l.source === currentNoteId || l.target === currentNoteId;
    });
    console.log('[MiniGraph] Related links for current note:', relatedLinks.length);
    if (relatedLinks.length > 0) {
      console.log('[MiniGraph] Related links:', relatedLinks);
    }
    
    miniGraphData = data;
    console.log('[MiniGraph] Rendering with nodes:', data.nodes.length, 'links:', data.links.length);
    renderMiniGraph();
    
    // Инициализируем контролы после загрузки данных (только один раз)
    if (!controlsInitialized) {
      initControls();
      controlsInitialized = true;
    }
    
    // Разблокируем инициализацию
    isInitializing = false;
  } catch (error) {
    console.error('[MiniGraph] Error loading graph:', error);
    showEmptyState('Ошибка загрузки графа');
    isInitializing = false;
  }
}

// Отображение пустого состояния
function showEmptyState(message) {
  const container = document.querySelector('.graph-sidebar__empty');
  if (container) {
    container.style.display = 'flex';
    const p = container.querySelector('p');
    if (p) {
      p.textContent = message;
    }
  }
}

// Рендер мини-графа
function renderMiniGraph() {
  if (!miniGraphData || !miniGraphSvg) {
    console.log('[MiniGraph] No data or SVG');
    return;
  }
  
  const container = document.getElementById('mini-graph-canvas');
  if (!container) {
    console.log('[MiniGraph] Container not found');
    return;
  }
  
  let width = container.clientWidth;
  let height = container.clientHeight;
  
  // Если размер нулевой, используем значения по умолчанию
  if (width === 0) width = 430;
  if (height === 0) height = 500;
  
  console.log('[MiniGraph] Rendering canvas:', width, 'x', height);
  
  // Скрываем пустое состояние
  const empty = container.querySelector('.graph-sidebar__empty');
  if (empty) empty.style.display = 'none';
  
  // Очищаем предыдущий граф
  miniGraphSvg.selectAll('*').remove();
  
  // Фильтруем: только текущая заметка и её прямые соседи
  const currentNode = miniGraphData.nodes.find(n => n.id === currentNoteId);
  if (!currentNode) {
    console.error('[MiniGraph] Current node not found!', currentNoteId);
    showEmptyState('Заметка не найдена');
    return;
  }
  
  console.log('[MiniGraph] Current node:', currentNode);
  
  const connectedNodeIds = new Set([currentNoteId]);
  
  console.log('[MiniGraph] Total links in data:', miniGraphData.links.length);
  console.log('[MiniGraph] Looking for connections to:', currentNoteId);
  
  miniGraphData.links.forEach((link, index) => {
    // API возвращает edges с source/target как строки ID
    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
    const targetId = typeof link.target === 'object' ? link.target.id : link.target;
    
    if (sourceId === currentNoteId || targetId === currentNoteId) {
      console.log(`[MiniGraph] Found connection ${index}:`, {
        source: sourceId,
        target: targetId,
        matches: sourceId === currentNoteId ? 'source' : 'target'
      });
    }
    
    if (sourceId === currentNoteId) {
      connectedNodeIds.add(targetId);
    }
    if (targetId === currentNoteId) {
      connectedNodeIds.add(sourceId);
    }
  });
  
  console.log('[MiniGraph] Connected node IDs:', Array.from(connectedNodeIds));
  
  const filteredNodes = miniGraphData.nodes.filter(n => connectedNodeIds.has(n.id));
  const filteredLinks = miniGraphData.links.filter(l => {
    const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
    const targetId = typeof l.target === 'object' ? l.target.id : l.target;
    return connectedNodeIds.has(sourceId) && connectedNodeIds.has(targetId);
  });
  
  console.log('[MiniGraph] Filtered nodes:', filteredNodes.length, 'links:', filteredLinks.length);
  
  // Если нет связанных узлов, показываем только текущую заметку
  if (filteredNodes.length === 1 && filteredLinks.length === 0) {
    console.log('[MiniGraph] Only current node, no connections');
  }
  
  // Создаем симуляцию
  miniGraphSimulation = d3.forceSimulation(filteredNodes)
    .force('link', d3.forceLink(filteredLinks).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => Math.max(16, getNodeRadius(d) + 6)));
  
  // Рисуем связи
  const link = miniGraphSvg.append('g')
    .selectAll('line')
    .data(filteredLinks)
    .join('line')
    .attr('stroke', d => ((d?.type || 'link') === 'tag' ? 'var(--text)' : 'var(--border-3)'))
    .attr('stroke-width', d => ((d?.type || 'link') === 'tag' ? 1.8 : 1.5))
    .attr('stroke-opacity', d => ((d?.type || 'link') === 'tag' ? 0.35 : 0.6))
    .attr('stroke-dasharray', d => ((d?.type || 'link') === 'tag' ? '8 6' : null));
  
  // Рисуем узлы
  const node = miniGraphSvg.append('g')
    .selectAll('circle')
    .data(filteredNodes)
    .join('circle')
    .attr('r', d => getNodeRadius(d))
    .attr('fill', d => d.color || 'var(--muted)')
    .attr('stroke', d => d.id === currentNoteId ? 'var(--accent)' : 'var(--card)')
    .attr('stroke-width', d => d.id === currentNoteId ? 3 : 2)
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      if (d.id !== currentNoteId) {
        console.log('[MiniGraph] Navigating to note:', d.id);
        
        // Показываем индикатор загрузки
        const empty = document.querySelector('.graph-sidebar__empty');
        if (empty) {
          empty.style.display = 'flex';
          const p = empty.querySelector('p');
          if (p) p.textContent = 'Переход к заметке...';
        }
        
        // Останавливаем симуляцию перед переходом
        if (miniGraphSimulation) {
          miniGraphSimulation.stop();
        }
        
        // Сбрасываем флаг перед переходом
        isInitializing = false;
        
        // Переходим к заметке
        window.location.href = `/?note_id=${d.id}`;
      }
    })
    .on('mouseenter', function(event, d) {
      if (d.id !== currentNoteId) {
        d3.select(this).attr('stroke', 'var(--accent)').attr('stroke-width', 3);
      }
    })
    .on('mouseleave', function(event, d) {
      if (d.id !== currentNoteId) {
        d3.select(this).attr('stroke', 'var(--card)').attr('stroke-width', 2);
      }
    })
    .call(drag(miniGraphSimulation));

  miniGraphNodeSelection = node;
  
  // Добавляем подписи
  const label = miniGraphSvg.append('g')
    .selectAll('text')
    .data(filteredNodes)
    .join('text')
    .text(d => {
      const title = d.title || d.id.substring(0, 8);
      return title.length > 20 ? title.substring(0, 20) + '...' : title;
    })
    .attr('font-size', d => d.id === currentNoteId ? '12px' : '10px')
    .attr('font-weight', d => d.id === currentNoteId ? '600' : '400')
    .attr('fill', 'var(--text)')
    .attr('text-anchor', 'middle')
    .attr('dy', d => d.id === currentNoteId ? -20 : -14)
    .style('pointer-events', 'none')
    .style('user-select', 'none');
  
  // Обновление позиций
  miniGraphSimulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    
    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y);
    
    label
      .attr('x', d => d.x)
      .attr('y', d => d.y);
  });
}

// Drag behavior
function drag(simulation) {
  function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
  }
  
  function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
  }
  
  function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
  }
  
  return d3.drag()
    .on('start', dragstarted)
    .on('drag', dragged)
    .on('end', dragended);
}

function getNodeRadius(node) {
  // Базовый размер зависит от sizeWeight/size узла
  const sizeWeight = node.size || 1;
  const base = node.id === currentNoteId 
    ? Math.max(10, sizeWeight * 10)  // Текущая заметка: минимум 10, масштабируется от sizeWeight
    : Math.max(6, sizeWeight * 8);   // Другие заметки: минимум 6
  return base;
}

// Инициализация контролов
function initControls() {
  console.log('[MiniGraph] Initializing controls with data:', miniGraphData ? 'loaded' : 'not loaded');
  
  // Кнопки размера узла на графе (sizeWeight)
  const zoomIn = document.getElementById('zoom-in');
  const zoomOut = document.getElementById('zoom-out');
  const zoomValue = document.getElementById('zoom-value');
  
  // Границы sizeWeight как в inspector
  const minWeight = 0.3;
  const maxWeight = 5;
  const step = 0.3;
  
  // Получаем текущий sizeWeight из данных заметки
  let currentSizeWeight = 1.0;
  
  function updateDisplay() {
    if (zoomValue) {
      zoomValue.textContent = currentSizeWeight.toFixed(1);
    }
  }
  
  // Загружаем актуальный sizeWeight из API
  async function loadSizeWeight() {
    try {
      const response = await fetch(`/api/notes/${currentNoteId}`);
      if (response.ok) {
        const note = await response.json();
        if (note.layoutHints && note.layoutHints.sizeWeight != null) {
          currentSizeWeight = note.layoutHints.sizeWeight;
        }
        updateDisplay();
        console.log('[MiniGraph] Loaded sizeWeight:', currentSizeWeight);
      }
    } catch (error) {
      console.error('[MiniGraph] Error loading sizeWeight:', error);
    }
  }
  
  loadSizeWeight();
  
  async function updateSizeWeight(delta) {
    const newWeight = Math.max(minWeight, Math.min(maxWeight, currentSizeWeight + delta));
    if (newWeight === currentSizeWeight) return;
    
    currentSizeWeight = Math.round(newWeight * 10) / 10; // округляем до 0.1
    updateDisplay();
    
    // Обновляем размер узла в данных мини-графа
    if (miniGraphData) {
      const currentNode = miniGraphData.nodes.find(n => n.id === currentNoteId);
      if (currentNode) {
        currentNode.size = currentSizeWeight;
      }
    }
    
    // Обновляем визуально на мини-графе
    if (miniGraphNodeSelection) {
      miniGraphNodeSelection
        .filter(d => d.id === currentNoteId)
        .transition()
        .duration(200)
        .attr('r', getNodeRadius({ id: currentNoteId, size: currentSizeWeight }));
    }
    
    // Обновляем collision force для корректного расположения узлов
    if (miniGraphSimulation) {
      const collision = miniGraphSimulation.force('collision');
      if (collision) {
        collision.radius(d => Math.max(16, getNodeRadius(d) + 6));
      }
      miniGraphSimulation.alpha(0.3).restart();
    }
    
    // Сохраняем на сервер через PATCH
    try {
      const response = await fetch(`/api/notes/${currentNoteId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layoutHints: { sizeWeight: currentSizeWeight }
        })
      });
      
      if (!response.ok) {
        console.error('[MiniGraph] Failed to update sizeWeight:', response.status);
      } else {
        console.log('[MiniGraph] sizeWeight updated to:', currentSizeWeight);
      }
    } catch (error) {
      console.error('[MiniGraph] Error updating sizeWeight:', error);
    }
  }
  
  if (zoomIn) {
    zoomIn.addEventListener('click', () => updateSizeWeight(step));
  }
  
  if (zoomOut) {
    zoomOut.addEventListener('click', () => updateSizeWeight(-step));
  }
  
  // Color picker для группы
  const colorPicker = document.getElementById('group-color-picker');
  if (colorPicker) {
    // Получаем текущий цвет группы
    let currentGroupKey = null;
    if (miniGraphData) {
      const currentNode = miniGraphData.nodes.find(n => n.id === currentNoteId);
      if (currentNode) {
        currentGroupKey = currentNode.group_key;
        if (currentNode.color) {
          colorPicker.value = currentNode.color;
        }
        console.log('[MiniGraph] Current group:', currentGroupKey, 'color:', currentNode.color);
      }
    }
    
    colorPicker.addEventListener('change', async (e) => {
      const newColor = e.target.value;
      console.log('[MiniGraph] Changing group color to:', newColor, 'for group:', currentGroupKey);
      
      if (!currentGroupKey) {
        console.error('[MiniGraph] No group key found');
        return;
      }
      
      try {
        // Отправляем запрос на обновление цвета группы через API
        const response = await fetch(`/api/graph/groups/${encodeURIComponent(currentGroupKey)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ color: newColor })
        });
        
        if (!response.ok) {
          throw new Error(`API error: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('[MiniGraph] Group color updated via API:', result);
        
        // Обновляем цвет всех узлов этой группы в данных
        if (miniGraphData) {
          miniGraphData.nodes.forEach(node => {
            if (node.group_key === currentGroupKey) {
              node.color = newColor;
            }
          });
        }
        
        // Обновляем цвет всех узлов этой группы в SVG
        miniGraphSvg.selectAll('circle')
          .filter(d => d.group_key === currentGroupKey)
          .transition()
          .duration(300)
          .attr('fill', newColor);
        
        console.log('[MiniGraph] All nodes in group updated with new color');
      } catch (error) {
        console.error('[MiniGraph] Error updating group color:', error);
      }
    });
  }
}

// Сбрасываем флаги при выгрузке страницы
window.addEventListener('beforeunload', () => {
  console.log('[MiniGraph] Page unloading, resetting flags...');
  isInitializing = false;
  if (miniGraphSimulation) {
    miniGraphSimulation.stop();
  }
});

// Запускаем при загрузке страницы
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    console.log('[MiniGraph] DOM loaded, initializing...');
    // Гарантируем сброс флага
    isInitializing = false;
    initMiniGraph();
  });
} else {
  console.log('[MiniGraph] DOM already loaded, initializing...');
  // Гарантируем сброс флага
  isInitializing = false;
  initMiniGraph();
}

// Также слушаем событие popstate для навигации назад/вперед
window.addEventListener('popstate', () => {
  console.log('[MiniGraph] Popstate event, re-initializing...');
  isInitializing = false;
  setTimeout(initMiniGraph, 100);
});

// Обработка bfcache (back-forward cache) — страница восстановлена из кеша
window.addEventListener('pageshow', (event) => {
  if (event.persisted) {
    console.log('[MiniGraph] Page restored from bfcache, re-initializing...');
    isInitializing = false;
    currentNoteId = null;
    miniGraphData = null;
    initMiniGraph();
  }
});
