const DEFAULT_COLOR = 'var(--accent)';

document.addEventListener('DOMContentLoaded', async () => {
  if (typeof window.d3 === 'undefined') {
    renderGraphError('Не удалось загрузить библиотеку визуализации.');
    return;
  }
  await loadGraph();
  await loadGroups();
});

async function loadGraph() {
  const response = await fetch('/api/graph');
  if (!response.ok) return;
  const data = await response.json();
  if (renderGraph(data)) {
    initToolbar();
  }
}

async function loadGroups() {
  const response = await fetch('/api/graph/groups');
  if (!response.ok) return;
  const data = await response.json();
  renderGroups(Array.isArray(data.groups) ? data.groups : []);
}

function renderGraphError(message) {
  const container = document.getElementById('graph-canvas');
  if (!container) return;
  container.innerHTML = '';
  const placeholder = document.createElement('div');
  placeholder.className = 'graph-empty';
  placeholder.textContent = message;
  container.appendChild(placeholder);
}

function renderGraph(data) {
  const container = document.getElementById('graph-canvas');
  if (!container) return false;

  const svg = d3.select('#graph-svg');
  const rect = container.getBoundingClientRect();
  const width = rect.width > 0 ? rect.width : 900;
  const height = rect.height > 0 ? rect.height : 600;

  svg.attr('width', width).attr('height', height);
  svg.selectAll('*').remove();
  container.querySelectorAll('.graph-empty').forEach((node) => node.remove());

  if (!Array.isArray(data.nodes) || data.nodes.length === 0) {
    renderGraphError('Граф пока пуст. Добавьте связи между заметками.');
    return false;
  }

  const nodes = data.nodes.map((node) => ({
    ...node,
    x: width / 2 + (Math.random() - 0.5) * width * 0.5,
    y: height / 2 + (Math.random() - 0.5) * height * 0.5,
  }));
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const edges = (data.edges || [])
    .map((edge) => {
      const source = nodesById.get(typeof edge.source === 'object' ? edge.source.id : edge.source);
      const target = nodesById.get(typeof edge.target === 'object' ? edge.target.id : edge.target);
      if (!source || !target) return null;
      return { ...edge, source, target };
    })
    .filter(Boolean);

  const zoomLayer = svg.append('g');

  const defs = svg.append('defs');
  const nodeGlow = defs
    .append('filter')
    .attr('id', 'node-glow')
    .attr('x', '-70%')
    .attr('y', '-70%')
    .attr('width', '240%')
    .attr('height', '240%')
    .attr('filterUnits', 'objectBoundingBox')
    .attr('color-interpolation-filters', 'sRGB');
  nodeGlow
    .append('feGaussianBlur')
    .attr('in', 'SourceGraphic')
    .attr('stdDeviation', '10')
    .attr('result', 'blur');
  nodeGlow
    .append('feColorMatrix')
    .attr('in', 'blur')
    .attr('type', 'matrix')
    .attr('values', '1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.35 0')
    .attr('result', 'glow');
  const feMerge = nodeGlow.append('feMerge');
  feMerge.append('feMergeNode').attr('in', 'glow');
  feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

  const link = zoomLayer
    .append('g')
    .selectAll('line')
    .data(edges)
    .join('line')
    .attr('class', (d) => (getEdgeType(d) === 'tag' ? 'edge-tag' : 'edge-link'))
    .attr('stroke-width', (d) =>
      getEdgeType(d) === 'tag' ? 1.8 : 1.2 + Math.max(0, (d.confidence || 0.5) * 2)
    )
    .attr('stroke', (d) =>
      getEdgeType(d) === 'tag' ? 'var(--muted)' : getLinkColor(d.source.color, d.target.color)
    )
    .attr('stroke-dasharray', (d) =>
      getEdgeType(d) === 'tag' ? '8 6' : null
    )
    .attr('stroke-opacity', (d) =>
      getEdgeType(d) === 'tag' ? 0.35 : 0.6
    );

  link
    .filter((d) => getEdgeType(d) === 'tag')
    .append('title')
    .text((d) => formatSharedTags(d.shared_tags));

  const nodeGroup = zoomLayer
    .append('g')
    .attr('stroke', 'var(--border)')
    .attr('stroke-width', 1.4)
    .selectAll('g')
    .data(nodes)
    .join('g');

  nodeGroup
    .append('title')
    .text((d) => `${d.title}\n📦 Блоков: ${d.blockCount}\n✍️ Символов: ${d.textSize}`);

  const getNodeRadius = (d) => 16 + Math.min(40, Math.max(0, d.sizeScore * 12));

  const node = nodeGroup
    .append('circle')
    .attr('r', (d) => getNodeRadius(d))
    .attr('fill', (d) => d.color || 'var(--accent)')
    .attr('filter', 'url(#node-glow)');



  const labels = zoomLayer
    .append('g')
    .selectAll('text')
    .data(nodes)
    .join('text')
    .attr('class', 'graph-label')
    .attr('text-anchor', 'middle')
    .attr('dy', '0.35em')
    .text((d) => truncate(d.title, 26));

  const tooltip = document.getElementById('graph-tooltip');
  const setTooltipContent = (node) => {
    if (!tooltip) return;
    tooltip.textContent = '';

    const title = document.createElement('strong');
    title.textContent = node.title || 'Без названия';
    tooltip.appendChild(title);
    tooltip.appendChild(document.createElement('br'));

    const lines = [
      `Блоков: ${node.blockCount}`,
      `Символов: ${node.textSize}`,
      `Вес узла: ${formatWeight(node.sizeWeight)}`,
      `Группа: ${node.group_label}`,
      `Обновлено: ${new Date(node.updatedAt).toLocaleString()}`,
    ];
    lines.forEach((line, idx) => {
      const span = document.createElement('span');
      span.textContent = line;
      tooltip.appendChild(span);
      if (idx < lines.length - 1) {
        tooltip.appendChild(document.createElement('br'));
      }
    });
  };

  nodeGroup.on('mouseover', (event, d) => {
    if (!tooltip) return;
    highlightNode({ target: d });
    tooltip.classList.remove('hidden');
    setTooltipContent(d);
    tooltip.style.left = `${event.pageX + 12}px`;
    tooltip.style.top = `${event.pageY + 12}px`;
  });

  nodeGroup.on('mouseout', () => {
    if (!tooltip) return;
    highlightNode(null);
    tooltip.classList.add('hidden');
  });

  nodeGroup.on('dblclick', (_, d) => {
    window.location.href = `/notes/${d.id}`;
  });

  const primaryEdges = edges.filter((edge) => getEdgeType(edge) === 'link');

  const simulation = d3
    .forceSimulation(nodes)
    .force('charge', d3.forceManyBody().strength(-260))
    .force('collision', d3.forceCollide().radius((d) => 28 + d.sizeScore * 10))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))
    .velocityDecay(0.45)
    .alphaDecay(0.05);

  if (primaryEdges.length) {
    simulation.force(
      'link',
      d3
        .forceLink(primaryEdges)
        .id((d) => d.id)
        .distance((d) => 200 - Math.min(100, (d.confidence || 0.4) * 60))
        .strength(0.6)
    );
  }

  simulation.on('tick', () => {
    link
      .attr('x1', (d) => d.source.x)
      .attr('y1', (d) => d.source.y)
      .attr('x2', (d) => d.target.x)
      .attr('y2', (d) => d.target.y);

    nodeGroup.attr('transform', (d) => `translate(${d.x}, ${d.y})`);
    labels.attr('x', (d) => d.x).attr('y', (d) => d.y);
  });

  nodeGroup.call(drag(simulation));

  simulation.on('end', () => {
    fitToView({ animate: true });
  });

  const zoomBehaviour = d3
    .zoom()
    .scaleExtent([0.2, 3])
    .on('zoom', (event) => zoomLayer.attr('transform', event.transform));

  svg.call(zoomBehaviour);

  function fitToView({ animate = true } = {}) {
    if (!nodes.length) return;
    const pad = Math.max(60, Math.min(width, height) * 0.08);
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    nodes.forEach((d) => {
      const r = getNodeRadius(d);
      minX = Math.min(minX, d.x - r);
      maxX = Math.max(maxX, d.x + r);
      minY = Math.min(minY, d.y - r);
      maxY = Math.max(maxY, d.y + r);
    });

    if (!Number.isFinite(minX) || !Number.isFinite(minY)) {
      return;
    }

    const boundsWidth = Math.max(1, maxX - minX + pad * 2);
    const boundsHeight = Math.max(1, maxY - minY + pad * 2);
    const scale = Math.max(0.2, Math.min(1, Math.min(width / boundsWidth, height / boundsHeight)));
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;
    const transform = d3.zoomIdentity
      .translate(width / 2 - scale * midX, height / 2 - scale * midY)
      .scale(scale);

    const target = animate ? svg.transition().duration(450) : svg;
    target.call(zoomBehaviour.transform, transform);
  }

  function highlightNode(payload) {
    const target = payload?.target;
    nodeGroup.classed('dimmed', (d) => target && d !== target);
    labels.classed('dimmed', (d) => target && d !== target);
    link
      .classed('dimmed', (d) => target && d.source !== target && d.target !== target)
      .classed('highlight', (d) => target && (d.source === target || d.target === target));
  }

  window.__graph = {
    nodes,
    edges,
    node,
    labels,
    link,
    svg,
    zoomBehaviour,
    simulation,
    fitToView,
    clusterColors: new Map(nodes.map((n) => [n.group_key, n.color ?? DEFAULT_COLOR])),
    clusterLabels: new Map(nodes.map((n) => [n.group_key, n.group_label])),
    renderLegend,
    getLinkColor,
  };

  renderLegend(window.__graph.clusterColors, window.__graph.clusterLabels);
  return true;
}

function initToolbar() {
  const store = window.__graph;
  if (!store) return;
  const { node, labels, link, zoomBehaviour, svg, fitToView } = store;
  const search = document.getElementById('graph-search');
  const resetBtn = document.getElementById('graph-reset');
  const toggleLabels = document.getElementById('graph-show-labels');

  search?.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase();
    if (!query) {
      node.classed('dimmed', false);
      labels.classed('dimmed', false);
      link.classed('dimmed', false);
      return;
    }
    node.classed('dimmed', (d) => !d.title.toLowerCase().includes(query));
    labels.classed('dimmed', (d) => !d.title.toLowerCase().includes(query));
    link.classed('dimmed', (d) => {
      const s = d.source.title.toLowerCase();
      const t = d.target.title.toLowerCase();
      return !(s.includes(query) || t.includes(query));
    });
  });

  resetBtn?.addEventListener('click', () => {
    search.value = '';
    node.classed('dimmed', false);
    labels.classed('dimmed', false);
    link.classed('dimmed', false);
    if (typeof fitToView === 'function') {
      fitToView({ animate: true });
    } else {
      svg.transition().duration(600).call(zoomBehaviour.transform, d3.zoomIdentity);
    }
    window.__graph?.simulation?.alpha(1).restart();
  });

  toggleLabels?.addEventListener('change', () => {
    const visible = toggleLabels.checked;
    labels.style('display', visible ? 'block' : 'none');
  });
}

function renderLegend(colorMap, labelMap = new Map()) {
  const panel = document.getElementById('graph-legend');
  if (!panel) return;
  panel.innerHTML = '';
  const entries = Array.from(colorMap.entries());
  if (!entries.length) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');
  entries.forEach(([cluster, color]) => {
    const item = document.createElement('span');
    item.className = 'graph-legend-item';
    item.style.setProperty('--legend-color', color);
    const swatch = document.createElement('span');
    swatch.className = 'graph-legend-swatch';
    const label = document.createTextNode(labelMap.get(cluster) || cluster);
    item.appendChild(swatch);
    item.appendChild(label);
    panel.appendChild(item);
  });
}

function renderGroups(groups) {
  const container = document.getElementById('graph-groups-list');
  if (!container) return;
  container.innerHTML = '';

  if (!groups.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'Группы не найдены.';
    container.appendChild(empty);
    return;
  }

  groups.forEach((group) => {
    const row = document.createElement('div');
    row.className = 'graph-group-row';

    const left = document.createElement('div');
    left.className = 'graph-group-left';

    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.value = group.label;
    nameInput.placeholder = 'Название группы';
    nameInput.className = 'graph-group-name-input';
    nameInput.addEventListener('blur', async () => {
      const next = nameInput.value.trim();
      if (!next || next === group.label) return;
      await updateGroupLabel(group.key, next);
    });
    nameInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        nameInput.blur();
      }
    });

    const count = document.createElement('span');
    count.className = 'graph-group-count';
    count.textContent = `${group.count} заметок`;

    left.append(nameInput, count);

    const controls = document.createElement('div');
    controls.className = 'graph-group-controls';
    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent')?.trim();
    colorInput.value = group.color || accent || colorInput.value;
    colorInput.addEventListener('change', async () => {
      await updateGroupColor(group.key, colorInput.value);
    });
    controls.appendChild(colorInput);

    row.append(left, controls);
    container.appendChild(row);
  });
}

async function updateGroupColor(key, color) {
  const res = await fetch(`/api/graph/groups/${encodeURIComponent(key)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ color }),
  });
  if (!res.ok) {
    alert('Не удалось обновить цвет группы');
    return;
  }
  const store = window.__graph;
  if (!store) return;
  store.clusterColors.set(key, color);
  store.node
    .filter((d) => d.group_key === key)
    .attr('fill', color)
    .each((d) => {
      d.color = color;
    });
  store.link.each(function (d) {
    if (getEdgeType(d) === 'tag') {
      return;
    }
    if (d.source.group_key === key || d.target.group_key === key) {
      d3.select(this).attr('stroke', getLinkColor(d.source.color, d.target.color));
    }
  });
  renderLegend(store.clusterColors, store.clusterLabels);
}

async function updateGroupLabel(key, label) {
  const res = await fetch(`/api/graph/groups/${encodeURIComponent(key)}/label`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label }),
  });
  if (!res.ok) {
    alert('Не удалось обновить название группы');
    return;
  }
  const store = window.__graph;
  if (!store) return;
  store.clusterLabels.set(key, label);
  store.node.filter((d) => d.group_key === key).each((d) => {
    d.group_label = label;
  });
  renderLegend(store.clusterColors, store.clusterLabels);
  await loadGroups();
}

function getLinkColor(colorA, colorB) {
  const fallback = 'var(--accent)';
  if (!colorA && !colorB) return fallback;
  if (colorA && colorA === colorB) return colorA;
  if (!colorA) return colorB || fallback;
  if (!colorB) return colorA;
  const a = hexToRgb(colorA);
  const b = hexToRgb(colorB);
  if (!a || !b) return fallback;
  return rgbToHex({
    r: (a.r + b.r) / 2,
    g: (a.g + b.g) / 2,
    b: (a.b + b.b) / 2,
  });
}

function hexToRgb(hex) {
  if (!hex) return null;
  const clean = hex.replace('#', '');
  const value = parseInt(clean.length === 3 ? clean.repeat(2) : clean, 16);
  if (Number.isNaN(value)) return null;
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
}

function rgbToHex({ r, g, b }) {
  const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
  return `#${[clamp(r), clamp(g), clamp(b)]
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('')}`;
}

function truncate(text, limit) {
  if (!text) return '';
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

function formatWeight(value) {
  const number = typeof value === 'number' ? value : Number.parseFloat(value);
  if (Number.isNaN(number)) return '1.0';
  return (Math.round(number * 10) / 10).toFixed(1);
}

function getEdgeType(edge) {
  return edge?.type || 'link';
}

function formatSharedTags(tags) {
  if (!Array.isArray(tags) || tags.length === 0) {
    return 'Общие теги: —';
  }
  return `Общие теги: ${tags.join(', ')}`;
}

function drag(simulation) {
  function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }

  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }

  function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }

  return d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended);
}
