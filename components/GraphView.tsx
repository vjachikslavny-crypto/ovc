"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation
} from "d3-force";
import type { GraphData } from "@/lib/graph";
import { getLinkReasonMeta } from "./linkReasonMeta";

type PositionedNode = GraphData["nodes"][number] & {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
};

type DrawableEdge = {
  id: string;
  reason: string;
  confidence: number;
  sourceId: string;
  targetId: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  stroke: string;
};


const MIN_HEIGHT = 420;

type Props = {
  data: GraphData;
};

export function GraphView({ data }: Props) {
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 760, height: 480 });
  const [nodes, setNodes] = useState<PositionedNode[]>([]);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const width = entry.contentRect.width;
      if (width === 0) return;
      setDimensions({
        width,
        height: Math.max(MIN_HEIGHT, Math.round(width * 0.6))
      });
    });

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const positionedNodes = useMemo(() => {
    if (data.nodes.length === 0) return [];
    return data.nodes.map((node, index) => ({
      ...node,
      x: ((index + 1) / (data.nodes.length + 1)) * dimensions.width,
      y: dimensions.height / 2
    }));
  }, [data.nodes, dimensions.height, dimensions.width]);

  useEffect(() => {
    if (positionedNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const simulationNodes = positionedNodes.map((node) => ({ ...node }));

    const simulation = forceSimulation(simulationNodes)
      .force("link",
        forceLink(data.edges)
          .id((node: { id: string }) => node.id)
          .distance(140)
      )
      .force("charge", forceManyBody().strength(-220))
      .force("center", forceCenter(dimensions.width / 2, dimensions.height / 2))
      .force("collide", forceCollide(40))
      .on("tick", () => {
        setNodes(
          simulationNodes.map((node) => ({
            ...node,
            x: clamp(node.x ?? dimensions.width / 2, 36, dimensions.width - 36),
            y: clamp(node.y ?? dimensions.height / 2, 36, dimensions.height - 36)
          }))
        );
      });

    return () => simulation.stop();
  }, [data.edges, dimensions.height, dimensions.width, positionedNodes]);

  const legend = useMemo(() => {
    const seen = new Set<string>();
    const items: Array<{ reason: string; label: string; stroke: string }> = [];
    for (const edge of data.edges) {
      if (seen.has(edge.reason)) continue;
      const meta = getLinkReasonMeta(edge.reason);
      items.push({ reason: edge.reason, label: meta.label, stroke: meta.stroke });
      seen.add(edge.reason);
    }
    return items;
  }, [data.edges]);

  const nodeIndex = useMemo(() => {
    return new Map(nodes.map((node) => [node.id, node]));
  }, [nodes]);

  const drawableEdges = useMemo(() => {
    if (nodes.length === 0) return [] as Array<DrawableEdge>;

    const results: DrawableEdge[] = [];
    for (const edge of data.edges) {
      const sourceId = resolveNodeId(edge.source, nodes);
      const targetId = resolveNodeId(edge.target, nodes);
      if (!sourceId || !targetId) continue;

      const source = nodeIndex.get(sourceId);
      const target = nodeIndex.get(targetId);
      if (!source || !target) continue;

      const meta = getLinkReasonMeta(edge.reason);
      const radiusSource = calculateNodeRadius(source.degree);
      const radiusTarget = calculateNodeRadius(target.degree);

      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux = dx / distance;
      const uy = dy / distance;

      const startX = source.x + ux * radiusSource;
      const startY = source.y + uy * radiusSource;
      const endX = target.x - ux * (radiusTarget + 6);
      const endY = target.y - uy * (radiusTarget + 6);

      results.push({
        id: edge.id,
        reason: edge.reason,
        confidence: edge.confidence ?? 0,
        sourceId,
        targetId,
        startX,
        startY,
        endX,
        endY,
        stroke: meta.stroke
      });
    }

    return results;
  }, [data.edges, nodeIndex, nodes]);

  const handleClick = (id: string) => {
    router.push(`/n/${id}`);
  };

  return (
    <div
      ref={containerRef}
      className="relative overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
      style={{ width: "100%" }}
    >
      {legend.length > 0 && (
        <div className="pointer-events-none absolute left-4 top-4 hidden flex-wrap gap-3 rounded-md border border-gray-200 bg-white/80 p-3 text-[11px] font-medium text-gray-600 backdrop-blur sm:flex">
          {legend.map((item) => (
            <span key={item.reason} className="flex items-center gap-2">
              <span
                className="h-1.5 w-6 rounded-full"
                style={{ backgroundColor: item.stroke }}
              />
              {item.label}
            </span>
          ))}
        </div>
      )}

      <svg width={dimensions.width} height={dimensions.height} className="bg-slate-50">
        <defs>
          {legend.map((item) => (
            <marker
              key={item.reason}
              id={`arrow-${item.reason}`}
              viewBox="0 0 10 10"
              refX="10"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={item.stroke} />
            </marker>
          ))}
        </defs>
        <g>
          {drawableEdges.map((edge) => renderEdge(edge, hovered))}
        </g>
        {nodes.map((node) => renderNode(node, { hovered, setHovered, handleClick }))}
      </svg>
    </div>
  );
}

function renderEdge(edge: DrawableEdge, hovered: string | null) {
  const isActive = hovered ? edge.sourceId === hovered || edge.targetId === hovered : false;
  const opacityBase = 0.3 + clamp(edge.confidence, 0, 1) * 0.3;
  const strokeOpacity = isActive ? 0.95 : opacityBase;
  const strokeWidth = isActive ? 2 : 1.2;

  return (
    <line
      key={edge.id}
      x1={edge.startX}
      y1={edge.startY}
      x2={edge.endX}
      y2={edge.endY}
      stroke={edge.stroke}
      strokeWidth={strokeWidth}
      strokeOpacity={strokeOpacity}
      markerEnd={`url(#arrow-${edge.reason})`}
    />
  );
}

function renderNode(
  node: PositionedNode,
  opts: { hovered: string | null; setHovered: (value: string | null) => void; handleClick: (id: string) => void }
) {
  const { hovered, setHovered, handleClick } = opts;
  const isHovered = hovered === node.id;
  const radius = calculateNodeRadius(node.degree);
  const fill = isHovered ? "#1d4ed8" : "#2563eb";
  const stroke = isHovered ? "#0f172a" : "#1e3a8a";

  const truncated = truncate(node.title, 24);

  return (
    <g key={node.id} transform={`translate(${node.x}, ${node.y})`} className="cursor-pointer">
      <circle
        r={radius}
        fill={fill}
        stroke={stroke}
        strokeWidth={isHovered ? 2 : 1}
        onMouseEnter={() => setHovered(node.id)}
        onMouseLeave={() => setHovered(null)}
        onClick={() => handleClick(node.id)}
      />
      <text
        textAnchor="middle"
        y={4}
        className="select-none text-xs font-medium text-white"
        onMouseEnter={() => setHovered(node.id)}
        onMouseLeave={() => setHovered(null)}
        onClick={() => handleClick(node.id)}
      >
        {truncated}
      </text>
      <title>{node.title}</title>
    </g>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function calculateNodeRadius(degree: number) {
  return 18 + Math.min(degree, 4) * 4;
}

function resolveNodeId(endpoint: unknown, nodes: PositionedNode[]): string | null {
  if (endpoint == null) return null;
  if (typeof endpoint === "string" || typeof endpoint === "number") {
    return String(endpoint);
  }
  if (typeof endpoint === "object") {
    if ("id" in endpoint && endpoint.id) {
      return String((endpoint as { id: string | number }).id);
    }
    if ("index" in endpoint && typeof (endpoint as { index: number }).index === "number") {
      const candidate = nodes[(endpoint as { index: number }).index];
      if (candidate) {
        return candidate.id;
      }
    }
  }
  return null;
}

function truncate(value: string, limit: number) {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 1)}…`;
}
