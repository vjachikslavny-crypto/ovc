import "dotenv/config";
import { db } from "../lib/db";
import {
  draftActions,
  messages,
  noteChunks,
  noteLinks,
  noteSources,
  noteTags,
  notes,
  reminders,
  sources
} from "../lib/schema";
import { reindexNote, createWikiLinks, createSemanticLinks } from "../lib/rag";

async function seed() {
  console.log("Seeding database...");

  await db.delete(noteSources);
  await db.delete(noteLinks);
  await db.delete(noteChunks);
  await db.delete(noteTags);
  await db.delete(messages);
  await db.delete(draftActions);
  await db.delete(reminders);
  await db.delete(sources);
  await db.delete(notes);

  const baseNotes = [
    {
      title: "Стратегия продукта OVC",
      contentMd: `# Стратегия продукта OVC

Мы строим рабочую среду, где заметки живут как граф знаний.

## Цели
- Доставить MVP за 4 недели.
- Подключить Postgres + pgvector.

[[RAG Поиск OVC]]`
    },
    {
      title: "RAG Поиск OVC",
      contentMd: `# RAG Поиск OVC

Система разбивает заметки на чанки и ищет ближайшие к запросу.

## Технические детали
- Embeddings-заглушка.
- vector(384) в pgvector.`
    },
    {
      title: "Этапы запуска",
      contentMd: `# Этапы запуска

1. Настроить БД.
2. Сгенерировать фронт + бэкенд.
3. Протестировать цепочку "чат → draft → commit".
`
    }
  ];

  const inserted = await db
    .insert(notes)
    .values(baseNotes)
    .returning({ id: notes.id, title: notes.title, contentMd: notes.contentMd });

  await db.insert(noteTags).values(
    inserted.flatMap((note, idx) => [
      {
        noteId: note.id,
        tag: idx === 0 ? "strategy" : "tech",
        weight: 1
      }
    ])
  );

  for (const note of inserted) {
    await reindexNote(note.id, note.contentMd);
    await createWikiLinks(note.id, note.contentMd);
  }

  for (const note of inserted) {
    await createSemanticLinks(note.id);
  }

  console.log(`Seed completed. Inserted ${inserted.length} notes.`);
}

seed()
  .then(() => {
    process.exit(0);
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
