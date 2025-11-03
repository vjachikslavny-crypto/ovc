import { eq } from "drizzle-orm";
import { db } from "./db";
import {
  noteChunks,
  noteLinks,
  noteSources,
  notes,
  sources
} from "./schema";
import { chunkMarkdown } from "./markdown";
import { embeddings } from "@/server/ai/embeddings";
import { cosineSimilarity } from "@/server/ai/similarity";
import { extractWikiLinks } from "./wiki";
import { buildSemanticLinks } from "./semantic";

export type SearchResult = {
  noteId: string;
  chunkId: string;
  text: string;
  score: number;
};

export async function reindexNote(noteId: string, content: string) {
  await db.delete(noteChunks).where(eq(noteChunks.noteId, noteId));
  const chunks = chunkMarkdown(content);
  if (chunks.length === 0) return;

  const vectors = await embeddings.embed(chunks);
  const rows = chunks.map((text, idx) => ({
    noteId,
    idx,
    text,
    embedding: vectors[idx]
  }));

  await db.insert(noteChunks).values(rows);
}

export async function ragSearch(query: string, limit = 5): Promise<SearchResult[]> {
  const rows = await db
    .select({
      id: noteChunks.id,
      noteId: noteChunks.noteId,
      text: noteChunks.text,
      embedding: noteChunks.embedding
    })
    .from(noteChunks)
    .limit(200);
  if (rows.length === 0) return [];

  const queryVector = (await embeddings.embed([query]))[0];

  const scored = rows
    .map((row) => ({
      noteId: row.noteId,
      chunkId: row.id,
      text: row.text,
      score: cosineSimilarity(queryVector, row.embedding as number[])
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  return scored;
}

export async function createWikiLinks(noteId: string, content: string) {
  const wikiNames = extractWikiLinks(content);
  if (wikiNames.length === 0) return;
  const relatedNotes = await db
    .select({
      id: notes.id,
      title: notes.title
    })
    .from(notes);

  const nameToId = new Map(
    relatedNotes.map((n) => [n.title.toLowerCase(), n.id])
  );

  const linkInserts: Array<{
    fromId: string;
    toId: string;
    reason: string;
    confidence: number;
  }> = [];

  for (const name of wikiNames) {
    const targetId = nameToId.get(name.toLowerCase());
    if (!targetId) continue;
    linkInserts.push({
      fromId: noteId,
      toId: targetId,
      reason: "wikilink",
      confidence: 0.95
    });
  }

  if (linkInserts.length > 0) {
    await db.insert(noteLinks).values(linkInserts).onConflictDoNothing();
  }
}

export async function createSemanticLinks(noteId: string) {
  const semanticLinks = await buildSemanticLinks(noteId);
  if (semanticLinks.length === 0) return;
  await db.insert(noteLinks).values(semanticLinks).onConflictDoNothing();
}

export async function attachSources(
  noteId: string,
  sourcePayloads: Array<{
    url: string;
    domain: string;
    title: string;
    published_at: string;
    summary: string;
  }>
) {
  if (sourcePayloads.length === 0) return;

  const insertedSources = await db
    .insert(sources)
    .values(
      sourcePayloads.map((item) => ({
        url: item.url,
        domain: item.domain,
        title: item.title,
        publishedAt: item.published_at,
        summary: item.summary
      }))
    )
    .returning({ id: sources.id });

  await db
    .insert(noteSources)
    .values(
      insertedSources.map((src) => ({
        noteId,
        sourceId: src.id,
        relevance: 0.9
      }))
    )
    .onConflictDoNothing();
}
