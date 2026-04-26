const dashboardRoot = document.querySelector('[data-home-dashboard]');

if (dashboardRoot) {
  const hasWorkspaceAccess = dashboardRoot.dataset.workspaceAccess === 'true';
  const state = {
    currentTab: 'notes',
    notes: [],
    totalNotes: 0,
    graph: null,
    graphRendered: false,
    graphSimulation: null,
  };

  const elements = {
    tabButtons: Array.from(document.querySelectorAll('[data-home-tab]')),
    tabPanels: Array.from(document.querySelectorAll('[data-home-panel]')),
    createNoteButton: document.getElementById('home-create-note'),
    recentNotes: document.getElementById('home-recent-notes'),
    noteGrid: document.getElementById('home-note-grid'),
    graphStats: document.getElementById('home-graph-stats'),
    graphInsights: document.getElementById('home-graph-insights'),
    graphCanvas: document.getElementById('home-graph-canvas'),
    graphSvg: document.getElementById('home-graph-svg'),
    graphEmpty: document.getElementById('home-graph-empty'),
  };

  initTabs();
  bindCreateNote();

  if (hasWorkspaceAccess) {
    loadWorkspace();
    window.addEventListener('resize', debounce(() => {
      if (state.currentTab === 'graph' && state.graph) {
        renderGraphPreview();
      }
    }, 180));
  }

  function initTabs() {
    elements.tabButtons.forEach((button) => {
      button.addEventListener('click', () => {
        const target = button.dataset.homeTab;
        if (!target || state.currentTab === target) return;
        state.currentTab = target;

        elements.tabButtons.forEach((item) => {
          const active = item.dataset.homeTab === target;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-selected', active ? 'true' : 'false');
        });

        elements.tabPanels.forEach((panel) => {
          const active = panel.dataset.homePanel === target;
          panel.classList.toggle('is-active', active);
          panel.hidden = !active;
        });

        if (target === 'graph' && state.graph) {
          requestAnimationFrame(() => {
            renderGraphPreview();
          });
        }
      });
    });
  }

  function bindCreateNote() {
    elements.createNoteButton?.addEventListener('click', async () => {
      elements.createNoteButton.setAttribute('disabled', 'disabled');
      try {
        const response = await fetch('/api/notes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: 'Новая заметка',
            blocks: [],
            styleTheme: document.body.dataset.theme || 'clean',
          }),
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const note = await response.json();
        window.location.href = `/notes/${note.id}`;
      } catch (error) {
        console.error('Failed to create note from dashboard', error);
        window.alert('Не удалось создать заметку. Попробуйте ещё раз.');
      } finally {
        elements.createNoteButton.removeAttribute('disabled');
      }
    });
  }

  async function loadWorkspace() {
    const [notesResult, graphResult] = await Promise.allSettled([
      fetchJson('/api/notes?limit=12&offset=0'),
      fetchJson('/api/graph'),
    ]);

    if (notesResult.status === 'fulfilled') {
      state.notes = Array.isArray(notesResult.value.items) ? notesResult.value.items : [];
      state.totalNotes = Number(notesResult.value.total || state.notes.length || 0);
      renderRecentNotes();
      renderNoteGrid();
    } else {
      console.error('Dashboard notes load failed', notesResult.reason);
      renderNotesError();
    }

    if (graphResult.status === 'fulfilled') {
      state.graph = graphResult.value;
      renderGraphStats();
      renderGraphInsights();
      if (state.currentTab === 'graph') {
        renderGraphPreview();
      }
    } else {
      console.error('Dashboard graph load failed', graphResult.reason);
      renderGraphFailure();
    }
  }

  async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  }

  function renderRecentNotes() {
    if (!elements.recentNotes) return;
    elements.recentNotes.innerHTML = '';

    if (!state.notes.length) {
      elements.recentNotes.appendChild(buildEmptyCard('Пока нет заметок', 'Создай первую заметку, и она появится здесь.'));
      return;
    }

    state.notes.slice(0, 5).forEach((note, index) => {
      const link = document.createElement('a');
      link.className = 'home-recent-item';
      link.href = `/notes/${note.id}`;

      const top = document.createElement('div');
      top.className = 'home-recent-item__top';

      const order = document.createElement('span');
      order.className = 'home-recent-item__index';
      order.textContent = String(index + 1).padStart(2, '0');

      const meta = document.createElement('span');
      meta.className = 'home-recent-item__meta';
      meta.textContent = relativeDate(note.updatedAt || note.updated_at);

      top.append(order, meta);

      const title = document.createElement('strong');
      title.className = 'home-recent-item__title';
      title.textContent = note.title || 'Без названия';

      const footer = document.createElement('span');
      footer.className = 'home-recent-item__footer';
      footer.textContent = themeLabel(note.styleTheme || note.style_theme);

      link.append(top, title, footer);
      elements.recentNotes.append(link);
    });
  }

  function renderNoteGrid() {
    if (!elements.noteGrid) return;
    elements.noteGrid.innerHTML = '';

    if (!state.notes.length) {
      elements.noteGrid.appendChild(buildEmptyCard('Ни одной заметки', 'После создания первой заметки здесь появится живая лента рабочей области.'));
      return;
    }

    state.notes.slice(0, 8).forEach((note) => {
      const card = document.createElement('a');
      card.className = 'home-note-card';
      card.href = `/notes/${note.id}`;

      const head = document.createElement('div');
      head.className = 'home-note-card__head';

      const style = document.createElement('span');
      style.className = 'home-note-card__tag';
      style.textContent = themeLabel(note.styleTheme || note.style_theme);

      const time = document.createElement('time');
      time.className = 'home-note-card__time';
      time.dateTime = note.updatedAt || note.updated_at || '';
      time.textContent = relativeDate(note.updatedAt || note.updated_at);

      head.append(style, time);

      const title = document.createElement('h3');
      title.className = 'home-note-card__title';
      title.textContent = note.title || 'Без названия';

      const summary = document.createElement('p');
      summary.className = 'home-note-card__summary';
      summary.textContent = `Обновлена ${absoluteDate(note.updatedAt || note.updated_at)}. Открыть и продолжить работу.`;

      const footer = document.createElement('div');
      footer.className = 'home-note-card__footer';
      footer.textContent = 'Открыть заметку';

      card.append(head, title, summary, footer);
      elements.noteGrid.append(card);
    });
  }

  function renderNotesError() {
    if (!elements.recentNotes || !elements.noteGrid) return;
    const message = buildEmptyCard('Не удалось загрузить заметки', 'Обнови страницу или попробуй снова позже.');
    elements.recentNotes.innerHTML = '';
    elements.noteGrid.innerHTML = '';
    elements.recentNotes.append(message.cloneNode(true));
    elements.noteGrid.append(message);
  }

  function renderGraphStats() {
    if (!elements.graphStats || !state.graph) return;
    const nodes = Array.isArray(state.graph.nodes) ? state.graph.nodes : [];
    const edges = Array.isArray(state.graph.edges) ? state.graph.edges : [];
    const groupCount = new Set(nodes.map((node) => node.group_label || 'Без группы')).size;

    elements.graphStats.innerHTML = '';
    [
      ['Узлы', nodes.length],
      ['Связи', edges.length],
      ['Группы', groupCount],
    ].forEach(([label, value]) => {
      const chip = document.createElement('span');
      chip.className = 'home-stat-chip';
      chip.textContent = `${label}: ${value}`;
      elements.graphStats.append(chip);
    });
  }

  function renderGraphInsights() {
    if (!elements.graphInsights || !state.graph) return;
    const nodes = Array.isArray(state.graph.nodes) ? [...state.graph.nodes] : [];
    const edges = Array.isArray(state.graph.edges) ? state.graph.edges : [];
    elements.graphInsights.innerHTML = '';

    if (!nodes.length) {
      const item = document.createElement('li');
      item.className = 'home-insight-item home-insight-item--muted';
      item.textContent = 'Сначала добавь заметки и связи между ними.';
      elements.graphInsights.append(item);
      return;
    }

    const groups = countGroups(nodes);
    const strongestNodes = nodes
      .sort((a, b) => Number(b.sizeScore || 0) - Number(a.sizeScore || 0))
      .slice(0, 3);

    const summaries = [
      `${nodes.length} заметок формируют рабочую карту.`,
      `Явных и теговых связей сейчас ${edges.length}.`,
      groups[0] ? `Самая насыщенная группа: ${groups[0][0]}.` : 'Группы появятся по мере роста карты.',
    ];

    summaries.forEach((text) => {
      const item = document.createElement('li');
      item.className = 'home-insight-item';
      item.textContent = text;
      elements.graphInsights.append(item);
    });

    strongestNodes.forEach((node) => {
      const item = document.createElement('li');
      item.className = 'home-insight-item home-insight-item--link';

      const title = document.createElement('span');
      title.textContent = node.title || 'Без названия';

      const group = document.createElement('small');
      group.textContent = node.group_label || 'Без группы';

      item.append(title, group);
      item.addEventListener('click', () => {
        window.location.href = `/notes/${node.id}`;
      });
      elements.graphInsights.append(item);
    });
  }

  function renderGraphFailure() {
    if (elements.graphEmpty) {
      elements.graphEmpty.hidden = false;
      elements.graphEmpty.textContent = 'Не удалось загрузить граф.';
    }
    if (elements.graphInsights) {
      elements.graphInsights.innerHTML = '';
      const item = document.createElement('li');
      item.className = 'home-insight-item home-insight-item--muted';
      item.textContent = 'Попробуй обновить страницу, когда сеть и сессия будут активны.';
      elements.graphInsights.append(item);
    }
  }

  function renderGraphPreview() {
    if (!state.graph || !elements.graphCanvas || !elements.graphSvg || typeof window.d3 === 'undefined') {
      renderGraphFailure();
      return;
    }

    const nodes = Array.isArray(state.graph.nodes) ? state.graph.nodes.map((node) => ({ ...node })) : [];
    const edges = Array.isArray(state.graph.edges) ? state.graph.edges : [];
    if (!nodes.length) {
      if (elements.graphEmpty) {
        elements.graphEmpty.hidden = false;
        elements.graphEmpty.textContent = 'Граф пока пуст. Добавь заметки и связи.';
      }
      return;
    }

    if (state.graphSimulation) {
      state.graphSimulation.stop();
      state.graphSimulation = null;
    }

    const svg = window.d3.select(elements.graphSvg);
    svg.selectAll('*').remove();

    const width = Math.max(elements.graphCanvas.clientWidth || 0, 420);
    const height = Math.max(elements.graphCanvas.clientHeight || 0, 420);
    svg.attr('width', width).attr('height', height);

    if (elements.graphEmpty) {
      elements.graphEmpty.hidden = true;
    }

    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const links = edges
      .map((edge) => {
        const source = nodeById.get(typeof edge.source === 'object' ? edge.source.id : edge.source);
        const target = nodeById.get(typeof edge.target === 'object' ? edge.target.id : edge.target);
        if (!source || !target) return null;
        return { ...edge, source, target };
      })
      .filter(Boolean);

    const layer = svg.append('g');

    const defs = svg.append('defs');
    const glow = defs.append('filter').attr('id', 'home-graph-glow');
    glow.append('feGaussianBlur').attr('stdDeviation', '6').attr('result', 'blur');
    const merge = glow.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');

    const linkSelection = layer
      .append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (edge) => (edge.type === 'tag' ? 'rgba(255,255,255,0.18)' : 'rgba(139,92,246,0.34)'))
      .attr('stroke-width', (edge) => (edge.type === 'tag' ? 1 : 1.5))
      .attr('stroke-dasharray', (edge) => (edge.type === 'tag' ? '6 6' : null));

    const nodeGroup = layer
      .append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('click', (_, node) => {
        window.location.href = `/notes/${node.id}`;
      });

    nodeGroup
      .append('circle')
      .attr('r', (node) => 8 + Math.min(16, Math.max(0, Number(node.sizeScore || 0) * 2.2)))
      .attr('fill', (node) => node.color || 'var(--accent)')
      .attr('stroke', 'rgba(255,255,255,0.7)')
      .attr('stroke-width', 1.25)
      .attr('filter', 'url(#home-graph-glow)');

    nodeGroup
      .append('text')
      .text((node) => truncate(node.title || 'Без названия', 18))
      .attr('class', 'home-graph-label')
      .attr('text-anchor', 'middle')
      .attr('dy', 26);

    const simulation = window.d3
      .forceSimulation(nodes)
      .force('charge', window.d3.forceManyBody().strength(-180))
      .force('center', window.d3.forceCenter(width / 2, height / 2))
      .force('collision', window.d3.forceCollide().radius((node) => 26 + Math.min(18, Number(node.sizeScore || 0) * 2.5)))
      .force(
        'link',
        window.d3
          .forceLink(links)
          .id((node) => node.id)
          .distance((edge) => (edge.type === 'tag' ? 120 : 90))
          .strength((edge) => (edge.type === 'tag' ? 0.08 : 0.22))
      );

    simulation.on('tick', () => {
      linkSelection
        .attr('x1', (edge) => edge.source.x)
        .attr('y1', (edge) => edge.source.y)
        .attr('x2', (edge) => edge.target.x)
        .attr('y2', (edge) => edge.target.y);

      nodeGroup.attr('transform', (node) => `translate(${node.x}, ${node.y})`);
    });

    state.graphSimulation = simulation;
    state.graphRendered = true;
  }

  function countGroups(nodes) {
    const counts = new Map();
    nodes.forEach((node) => {
      const key = node.group_label || 'Без группы';
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }

  function buildEmptyCard(title, text) {
    const card = document.createElement('div');
    card.className = 'home-empty-card';

    const heading = document.createElement('strong');
    heading.textContent = title;

    const body = document.createElement('p');
    body.textContent = text;

    card.append(heading, body);
    return card;
  }

  function themeLabel(value) {
    const normalized = String(value || 'clean').trim().toLowerCase();
    const labels = {
      clean: 'Clean',
      brief: 'Brief',
      default: 'Default',
      dark: 'Dark',
      milk: 'Milk',
      light: 'Light',
      white: 'White',
      'pastel-blue': 'Pastel',
    };
    return labels[normalized] || normalized;
  }

  function truncate(value, maxLength) {
    if (!value || value.length <= maxLength) return value;
    return `${value.slice(0, Math.max(0, maxLength - 1))}…`;
  }

  function absoluteDate(value) {
    if (!value) return 'недавно';
    const date = new Date(value);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
    });
  }

  function relativeDate(value) {
    if (!value) return 'только что';
    const date = new Date(value);
    const diff = Date.now() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'только что';
    if (minutes < 60) return `${minutes} мин назад`;
    if (hours < 24) return `${hours} ч назад`;
    if (days < 7) return `${days} дн назад`;
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  }

  function debounce(fn, delay) {
    let timeoutId = null;
    return (...args) => {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => fn(...args), delay);
    };
  }
}
