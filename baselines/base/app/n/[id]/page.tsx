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
import { MarkdownView } from "@/components/MarkdownView";
import { SourcesTable } from "@/components/SourcesTable";

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

  const backlinks = await db
    .select({
      id: notes.id,
      title: notes.title
    })
    .from(noteLinks)
    .leftJoin(notes, eq(noteLinks.fromId, notes.id))
    .where(eq(noteLinks.toId, id));

  const chatLink = (prompt: string) =>
    `/chat?prompt=${encodeURIComponent(prompt)}&noteId=${id}`;

  return (
    <div className="space-y-6">
      <header className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-gray-800">{note.title}</h2>
            <span className="text-xs text-gray-500">
              Обновлено {note.updatedAt.toLocaleString()}
            </span>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <Link
              href={chatLink(`Дополни заметку ${note.title}`)}
              className="rounded-md border border-gray-300 px-3 py-1 hover:bg-gray-100"
            >
              Дополни
            </Link>
            <Link
              href={chatLink(`Сделай сводку для ${note.title}`)}
              className="rounded-md border border-gray-300 px-3 py-1 hover:bg-gray-100"
            >
              Сводка
            </Link>
            <Link
              href={chatLink(`Проверь факты для ${note.title}`)}
              className="rounded-md border border-gray-300 px-3 py-1 hover:bg-gray-100"
            >
              Проверка фактов
            </Link>
          </div>
        </div>
      </header>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <MarkdownView content={note.contentMd} />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700">Теги</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {tagList.length > 0 ? (
              tagList.map((tag) => (
                <span
                  key={tag.tag}
                  className="rounded-full bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700"
                >
                  #{tag.tag}
                </span>
              ))
            ) : (
              <span className="text-sm text-gray-500">
                Теги не назначены. Попросите агента добавить метки.
              </span>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700">Бэклинки</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {backlinks.length > 0 ? (
              backlinks.map((link) =>
                link.id && link.title ? (
                  <li key={link.id}>
                    <Link
                      href={`/n/${link.id}`}
                      className="text-blue-600 hover:text-blue-800"
                    >
                      {link.title}
                    </Link>
                  </li>
                ) : null
              )
            ) : (
              <li className="text-gray-500">Пока нет обратных ссылок.</li>
            )}
          </ul>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Источники</h3>
        <SourcesTable sources={sourceList} />
      </section>
    </div>
  );
}
