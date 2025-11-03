import Link from "next/link";
import { notFound } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  noteLinks,
  noteSources,
  noteTags,
  notes,
  sources
} from "@/lib/schema";
import { SourcesTable } from "@/components/SourcesTable";
import { EditableNoteContent } from "@/components/EditableNoteContent";
import { TagPill } from "@/components/TagPill";
import { ConnectionsPanel } from "@/components/ConnectionsPanel";

type NotePageProps = {
  params: { id: string };
};

export default async function NoteDetailPage({ params }: NotePageProps) {
  const { id } = params;

  const noteRecords = await db
    .select({
      id: notes.id,
      title: notes.title,
      contentMd: notes.contentMd,
      updatedAt: notes.updatedAt
    })
    .from(notes)
    .where(eq(notes.id, id))
    .limit(1);

  const note = noteRecords[0];
  if (!note) {
    notFound();
  }

  const tagList = await db
    .select({
      tag: noteTags.tag
    })
    .from(noteTags)
    .where(eq(noteTags.noteId, id));

  const sourceList = await db
    .select({
      id: sources.id,
      url: sources.url,
      domain: sources.domain,
      title: sources.title,
      summary: sources.summary,
      publishedAt: sources.publishedAt
    })
    .from(noteSources)
    .leftJoin(sources, eq(noteSources.sourceId, sources.id))
    .where(eq(noteSources.noteId, id));

  const outbound = await db
    .select({
      linkId: noteLinks.id,
      noteId: notes.id,
      title: notes.title,
      reason: noteLinks.reason,
      confidence: noteLinks.confidence
    })
    .from(noteLinks)
    .leftJoin(notes, eq(noteLinks.toId, notes.id))
    .where(eq(noteLinks.fromId, id));

  const inbound = await db
    .select({
      linkId: noteLinks.id,
      noteId: notes.id,
      title: notes.title,
      reason: noteLinks.reason,
      confidence: noteLinks.confidence
    })
    .from(noteLinks)
    .leftJoin(notes, eq(noteLinks.fromId, notes.id))
    .where(eq(noteLinks.toId, id));

  const chatLink = (prompt: string) =>
    `/chat?prompt=${encodeURIComponent(prompt)}&noteId=${id}`;

  const quickActions = [
    {
      label: "Дополни заметку",
      href: chatLink(`Дополни заметку ${note.title}`)
    },
    {
      label: "Сделай сводку",
      href: chatLink(`Сделай сводку для ${note.title}`)
    },
    {
      label: "Проверь факты",
      href: chatLink(`Проверь факты для ${note.title}`)
    },
    {
      label: "Добавь информацию из интернета",
      href: chatLink(`Добавь информацию из интернета в заметку ${note.title}`)
    }
  ];

  const outboundConnections = outbound
    .filter((link) => link.noteId && link.title)
    .map((link) => ({
      id: link.noteId!,
      title: link.title!,
      reason: link.reason,
      confidence: link.confidence
    }));

  const inboundConnections = inbound
    .filter((link) => link.noteId && link.title)
    .map((link) => ({
      id: link.noteId!,
      title: link.title!,
      reason: link.reason,
      confidence: link.confidence
    }));

  const metrics = [
    { label: "Теги", value: tagList.length },
    { label: "Источники", value: sourceList.length },
    {
      label: "Связи",
      value: outboundConnections.length + inboundConnections.length
    }
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div className="space-y-6">
          <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <EditableNoteContent
              noteId={note.id}
              initialTitle={note.title}
              initialContent={note.contentMd}
              updatedAt={note.updatedAt.toISOString()}
            />
            <dl className="mt-6 grid gap-3 sm:grid-cols-3">
              {metrics.map((metric) => (
                <div
                  key={metric.label}
                  className="rounded-md border border-gray-100 bg-gray-50 px-3 py-3"
                >
                  <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                    {metric.label}
                  </dt>
                  <dd className="mt-1 text-xl font-semibold text-gray-800">{metric.value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-700">Источники</h3>
                <p className="text-xs text-gray-500">
                  Агент добавляет ссылки на материалы из Tavily или вручную.
                </p>
              </div>
              <Link
                href={chatLink(`Добавь информацию из интернета в заметку ${note.title}`)}
                className="hidden rounded-md border border-gray-300 px-3 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-100 lg:inline-flex"
              >
                Добавить источники
              </Link>
            </div>
            <SourcesTable sources={sourceList} />
          </section>
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700">Быстрые действия</h3>
            <ul className="mt-3 space-y-2 text-sm">
              {quickActions.map((action) => (
                <li key={action.label}>
                  <Link
                    href={action.href}
                    className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2 transition hover:border-blue-400 hover:text-blue-600"
                  >
                    <span>{action.label}</span>
                    <span className="text-xs text-gray-400">→</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-700">Теги</h3>
              <Link
                href={chatLink(`Добавь теги для заметки ${note.title}`)}
                className="text-xs font-semibold text-blue-600 hover:text-blue-700"
              >
                Попросить агента
              </Link>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {tagList.length > 0 ? (
                tagList.map((tag) => <TagPill key={tag.tag} value={tag.tag} />)
              ) : (
                <span className="text-sm text-gray-500">
                  Теги не назначены. Запросите метки у агента.
                </span>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700">Интеграция модели</h3>
            <p className="mt-2 text-xs text-gray-500">
              Здесь появится управление моделью, когда подключите свой inference: переключатели режимов, контекст и телеметрию.
            </p>
          </div>
        </aside>
      </div>

      <ConnectionsPanel outbound={outboundConnections} inbound={inboundConnections} />
    </div>
  );
}
