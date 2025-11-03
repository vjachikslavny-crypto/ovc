import type { Note, NoteLink } from "./schema";

export type GraphNode = {
  id: string;
  title: string;
  degree: number;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  reason: string;
  confidence: number;
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export function buildGraph(notes: Note[], links: NoteLink[]): GraphData {
  const nodeMap = new Map<string, GraphNode>();
  for (const note of notes) {
    nodeMap.set(note.id, {
      id: note.id,
      title: note.title,
      degree: 0
    });
  }

  const edges: GraphEdge[] = [];
  for (const link of links) {
    if (!nodeMap.has(link.fromId) || !nodeMap.has(link.toId)) continue;
    const edgeId = `${link.fromId}-${link.toId}-${link.id}`;
    edges.push({
      id: edgeId,
      source: link.fromId,
      target: link.toId,
      reason: link.reason,
      confidence: link.confidence ?? 0.5
    });
    nodeMap.get(link.fromId)!.degree += 1;
    nodeMap.get(link.toId)!.degree += 1;
  }

  return {
    nodes: Array.from(nodeMap.values()),
    edges
  };
}
