import Link from "next/link";
import { desc } from "drizzle-orm";
import { db } from "@/lib/db";
import { noteTags, notes } from "@/lib/schema";
import { NoteCard } from "@/components/NoteCard";
import { NoteSearch } from "@/components/NoteSearch";

export default async function NotesPage() {
  const noteList = await db
    .select({
      id: notes.id,
      title: notes.title,
      contentMd: notes.contentMd,
      updatedAt: notes.updatedAt
    })
    .from(notes)
    .orderBy(desc(notes.updatedAt))
    .limit(50);

  const tagList = await db
    .select({
      noteId: noteTags.noteId,
      tag: noteTags.tag
    })
    .from(noteTags);

  const tagsByNote = new Map<string, string[]>();
  for (const tag of tagList) {
    const entry = tagsByNote.get(tag.noteId) ?? [];
    entry.push(tag.tag);
    tagsByNote.set(tag.noteId, entry);
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-800">Заметки</h2>
          <p className="text-sm text-gray-600">
            Управляйте заметками и ищите нужный контент через семантический поиск.
          </p>
        </div>
        <Link
          href="/chat"
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Создать заметку через чат
        </Link>
      </section>

      <NoteSearch />

      <div className="grid gap-4 md:grid-cols-2">
        {noteList.map((note) => (
          <NoteCard
            key={note.id}
            id={note.id}
            title={note.title}
            contentMd={note.contentMd}
            updatedAt={note.updatedAt}
            tags={tagsByNote.get(note.id)}
          />
        ))}
        {noteList.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-500">
            Пока нет заметок. Начните с команды “Создай заметку ...” в чате.
          </div>
        )}
      </div>
    </div>
  );
}
