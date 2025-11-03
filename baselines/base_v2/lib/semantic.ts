import { eq, ne } from "drizzle-orm";
import { db } from "./db";
import { notes } from "./schema";
import { embeddings } from "@/server/ai/embeddings";
import { cosineSimilarity } from "@/server/ai/similarity";

const SEMANTIC_THRESHOLD = 0.78;

export async function buildSemanticLinks(noteId: string) {
  const targetRows = await db
    .select({
      id: notes.id,
      title: notes.title,
      contentMd: notes.contentMd
    })
    .from(notes)
    .where(eq(notes.id, noteId))
    .limit(1);
  const target = targetRows[0];
  if (!target) return [];

  const candidates = await db
    .select({
      id: notes.id,
      title: notes.title,
      contentMd: notes.contentMd
    })
    .from(notes)
    .where(ne(notes.id, noteId));
  if (candidates.length === 0) return [];

  const payloads = [
    `${target.title}\n${target.contentMd.slice(0, 600)}`
  ];
  for (const candidate of candidates) {
    payloads.push(`${candidate.title}\n${candidate.contentMd.slice(0, 600)}`);
  }

  const vectors = await embeddings.embed(payloads);
  const targetVector = vectors[0];
  const results: Array<{
    fromId: string;
    toId: string;
    reason: string;
    confidence: number;
  }> = [];

  candidates.forEach((candidate, idx) => {
    const similarity = cosineSimilarity(targetVector, vectors[idx + 1]);
    if (similarity >= SEMANTIC_THRESHOLD) {
      results.push({
        fromId: noteId,
        toId: candidate.id,
        reason: "semantic",
        confidence: Number(similarity.toFixed(3))
      });
    }
  });

  return results;
}
