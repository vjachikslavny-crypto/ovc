"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  forceCenter,
  forceLink,
  forceManyBody,
  forceSimulation
} from "d3-force";
import type { GraphData } from "@/lib/graph";

type PositionedNode = GraphData["nodes"][number] & {
  x: number;
  y: number;
};

type Props = {
  data: GraphData;
};

export function GraphView({ data }: Props) {
  const router = useRouter();
  const [nodes, setNodes] = useState<PositionedNode[]>([]);
  const [edges, setEdges] = useState(data.edges);

  const width = 760;
  const height = 480;

  const initialNodes = useMemo(
    () =>
      data.nodes.map((node, index) => ({
        ...node,
        x: (index / data.nodes.length) * width,
        y: (index / data.nodes.length) * height
      })),
    [data.nodes, width, height]
  );

  useEffect(() => {
    const simulation = forceSimulation(initialNodes)
      .force(
        "link",
        forceLink(data.edges)
          .id((node: any) => node.id)
          .distance(120)
      )
      .force("charge", forceManyBody().strength(-180))
      .force("center", forceCenter(width / 2, height / 2))
      .on("tick", () => {
        setNodes(
          initialNodes.map((node) => ({
            ...node,
            x: Math.max(40, Math.min(width - 40, node.x ?? width / 2)),
            y: Math.max(40, Math.min(height - 40, node.y ?? height / 2))
          }))
        );
      });

    setEdges(data.edges);

    return () => {
      simulation.stop();
    };
  }, [data.edges, initialNodes, width, height]);

  const handleClick = (id: string) => {
    router.push(`/n/${id}`);
  };

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <svg width={width} height={height} className="bg-gray-50">
        <g stroke="#CBD5F5" strokeWidth={1.2}>
          {edges.map((edge) => {
            const sourcePos = resolveEndpoint(edge.source, nodes);
            const targetPos = resolveEndpoint(edge.target, nodes);
            if (!sourcePos || !targetPos) return null;
            return (
              <line
                key={edge.id}
                x1={sourcePos.x}
                y1={sourcePos.y}
                x2={targetPos.x}
                y2={targetPos.y}
                strokeOpacity={0.6}
              />
            );
          })}
        </g>
        {nodes.map((node) => (
          <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
            <circle
              r={20 + node.degree * 4}
              className="cursor-pointer fill-blue-500 hover:fill-blue-600"
              onClick={() => handleClick(node.id)}
            />
            <text
              textAnchor="middle"
              y={4}
              className="cursor-pointer text-xs font-medium text-white"
              onClick={() => handleClick(node.id)}
            >
              {node.title.length > 18
                ? `${node.title.slice(0, 16)}…`
                : node.title}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function resolveEndpoint(
  endpoint: string | number | PositionedNode | { id: string; x: number; y: number },
  nodes: PositionedNode[]
) {
  if (endpoint && typeof endpoint === "object" && "x" in endpoint && "y" in endpoint) {
    return endpoint as { x: number; y: number };
  }
  const id = String(endpoint);
  return nodes.find((node) => node.id === id);
}
