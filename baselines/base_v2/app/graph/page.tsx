import { db } from "@/lib/db";
import { noteLinks, notes } from "@/lib/schema";
import { buildGraph } from "@/lib/graph";
import { GraphView } from "@/components/GraphView";

export default async function GraphPage() {
  const noteList = await db
    .select({
      id: notes.id,
      title: notes.title,
      contentMd: notes.contentMd
    })
    .from(notes);

  const linkList = await db
    .select({
      id: noteLinks.id,
      fromId: noteLinks.fromId,
      toId: noteLinks.toId,
      reason: noteLinks.reason,
      confidence: noteLinks.confidence
    })
    .from(noteLinks);

  const graph = buildGraph(noteList, linkList);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800">Граф связей</h2>
        <p className="text-sm text-gray-600">
          Узлы — заметки, рёбра — ссылки. Кликните на узел, чтобы открыть заметку.
        </p>
      </div>
      <GraphView data={graph} />
    </div>
  );
}
