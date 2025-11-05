import { desc, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  draftActions,
  messages,
  noteLinks,
  noteSources,
  notes,
  sources
} from "@/lib/schema";

function jsonPreview(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch (error) {
    return String(value);
  }
}

export default async function MonitorPage() {
  const [logItems, draftItem, noteList, linkList, sourceList] = await Promise.all([
    db
      .select({
        id: messages.id,
        role: messages.role,
        text: messages.text,
        meta: messages.meta,
        createdAt: messages.createdAt
      })
      .from(messages)
      .orderBy(desc(messages.createdAt))
      .limit(20),
    db
      .select({
        id: draftActions.id,
        payload: draftActions.payload,
        createdAt: draftActions.createdAt
      })
      .from(draftActions)
      .orderBy(desc(draftActions.createdAt))
      .limit(1),
    db
      .select({
        id: notes.id,
        title: notes.title,
        updatedAt: notes.updatedAt
      })
      .from(notes)
      .orderBy(desc(notes.updatedAt))
      .limit(10),
    db
      .select({
        id: noteLinks.id,
        fromId: noteLinks.fromId,
        toId: noteLinks.toId,
        reason: noteLinks.reason,
        confidence: noteLinks.confidence
      })
      .from(noteLinks)
      .orderBy(desc(noteLinks.id))
      .limit(15),
    db
      .select({
        noteId: noteSources.noteId,
        sourceId: noteSources.sourceId,
        relevance: noteSources.relevance,
        title: sources.title,
        domain: sources.domain,
        publishedAt: sources.publishedAt
      })
      .from(noteSources)
      .leftJoin(sources, eq(noteSources.sourceId, sources.id))
      .orderBy(desc(noteSources.noteId))
      .limit(10)
  ]);

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800">Активность агента</h2>
        <p className="text-sm text-gray-600">
          Здесь отображаются последние сообщения, черновики и связи между заметками.
        </p>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-semibold text-gray-700">Последние сообщения</h3>
        <div className="mt-3 space-y-4">
          {logItems.length === 0 && (
            <div className="rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
              Журнал сообщений пуст. Отправьте запрос агенту в разделе &quot;Чат&quot;.
            </div>
          )}
          {logItems.map((item) => (
            <article
              key={item.id}
              className="rounded-md border border-gray-100 bg-gray-50 p-4 text-sm"
            >
              <header className="flex items-center justify-between">
                <span className="font-medium text-gray-700">
                  {item.role === "agent" ? "Агент" : "Пользователь"}
                </span>
                <time className="text-xs text-gray-500">
                  {item.createdAt.toLocaleString()}
                </time>
              </header>
              <p className="mt-2 whitespace-pre-wrap text-gray-800">{item.text}</p>
              {item.meta != null && (
                <pre className="mt-3 overflow-x-auto rounded-md bg-white p-3 text-xs text-gray-700">
                  {String(jsonPreview(item.meta))}
                </pre>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-semibold text-gray-700">Текущий черновик действий</h3>
        {draftItem.length === 0 ? (
          <div className="mt-3 rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
            Черновик отсутствует. Сформируйте запрос в чате, чтобы агент предложил действия.
          </div>
        ) : (
          draftItem.map((draft) => (
            <div key={draft.id} className="mt-3 space-y-2">
              <div className="text-xs text-gray-500">
                Создан: {draft.createdAt.toLocaleString()}
              </div>
              <pre className="overflow-x-auto rounded-md bg-gray-50 p-4 text-xs text-gray-700">
                {jsonPreview(draft.payload)}
              </pre>
            </div>
          ))
        )}
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-semibold text-gray-700">Недавние заметки</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {noteList.map((note) => (
            <div key={note.id} className="rounded-md border border-gray-100 p-4">
              <div className="text-sm font-semibold text-gray-800">{note.title}</div>
              <div className="mt-1 text-xs text-gray-500">
                Обновлено: {note.updatedAt.toLocaleString()}
              </div>
              <a
                href={`/n/${note.id}`}
                className="mt-2 inline-flex text-xs text-blue-600 hover:text-blue-800"
              >
                Открыть заметку
              </a>
            </div>
          ))}
          {noteList.length === 0 && (
            <div className="rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
              Заметки ещё не созданы.
            </div>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-semibold text-gray-700">Связи между заметками</h3>
        <div className="mt-3 space-y-3 text-sm">
          {linkList.length === 0 && (
            <div className="rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
              Связи пока не найдены. Агент добавит их после применения черновика.
            </div>
          )}
          {linkList.map((link) => (
            <div
              key={link.id}
              className="rounded-md border border-gray-100 bg-gray-50 p-3 leading-relaxed text-gray-700"
            >
              <div>
                <span className="font-semibold text-gray-800">От:</span>{" "}
                <a href={`/n/${link.fromId}`} className="text-blue-600 hover:text-blue-800">
                  {link.fromId}
                </a>
              </div>
              <div>
                <span className="font-semibold text-gray-800">К:</span>{" "}
                <a href={`/n/${link.toId}`} className="text-blue-600 hover:text-blue-800">
                  {link.toId}
                </a>
              </div>
              <div className="text-xs text-gray-500">
                Причина: {link.reason} · Уверенность: {(link.confidence ?? 0) * 100}%
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <h3 className="text-base font-semibold text-gray-700">Источники</h3>
        <div className="mt-3 space-y-3 text-sm">
          {sourceList.length === 0 && (
            <div className="rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
              Источники ещё не добавлены. Попросите агента обогатить заметку ссылками.
            </div>
          )}
          {sourceList.map((source) => (
            <div
              key={`${source.noteId}-${source.sourceId}`}
              className="rounded-md border border-gray-100 bg-gray-50 p-3 leading-relaxed text-gray-700"
            >
              <div>
                <span className="font-semibold text-gray-800">Заметка:</span>{" "}
                <a href={`/n/${source.noteId}`} className="text-blue-600 hover:text-blue-800">
                  {source.noteId}
                </a>
              </div>
              <div>
                <span className="font-semibold text-gray-800">Источник:</span>{" "}
                {source.title ? (
                  <span>
                    {source.title} ({source.domain})
                  </span>
                ) : (
                  <span>Без названия</span>
                )}
              </div>
              <div className="text-xs text-gray-500">
                Релевантность: {(source.relevance ?? 0) * 100}%, дата публикации:{" "}
                {source.publishedAt ? new Date(source.publishedAt).toLocaleDateString() : "—"}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
