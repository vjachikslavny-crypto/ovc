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
  const avgDegree = graph.nodes.length > 0
    ? (graph.edges.length * 2) / graph.nodes.length
    : 0;
  const metrics = [
    { label: "Заметок", value: graph.nodes.length },
    { label: "Связей", value: graph.edges.length },
    { label: "Средняя степень", value: avgDegree.toFixed(1) }
  ];

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">Граф связей</h2>
            <p className="text-sm text-gray-600">
              Узлы — заметки, рёбра — связи между ними. Наведите курсор или кликните по узлу, чтобы открыть заметку.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center text-sm">
            {metrics.map((metric) => (
              <div key={metric.label} className="rounded-md border border-gray-100 bg-gray-50 px-4 py-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  {metric.label}
                </div>
                <div className="mt-1 text-lg font-semibold text-gray-800">{metric.value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <GraphView data={graph} />
    </div>
  );
}
