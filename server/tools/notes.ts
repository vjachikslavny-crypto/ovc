import { randomUUID as uuid } from "crypto";
import { eq, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  noteLinks,
  noteTags,
  notes,
  sources,
  noteSources
} from "@/lib/schema";
import { reindexNoteWithClient } from "@/lib/rag";

type CreateNoteInput = {
  title: string;
  content_md: string;
};

type UpdateNoteInput = {
  id: string;
  patch_md: string;
  position: "append" | "prepend";
};

type AddLinkInput = {
  from_id: string;
  to_title: string;
  reason: string;
  confidence: number;
};

type AddTagInput = {
  note_id: string;
  tag: string;
  weight?: number;
};

type AddSourceInput = {
  note_id: string;
  source: {
    url: string;
    title: string;
    domain: string;
    published_at: string;
    summary: string;
  };
};

type DbClient = typeof db | any;

function getClient(client?: DbClient) {
  return client ?? db;
}

export async function createNote({ title, content_md }: CreateNoteInput, client?: DbClient) {
  const id = uuid();
  const safeTitle = title.trim();
  const content = content_md ?? "";

  const ctx = getClient(client);

  await ctx.insert(notes).values({ id, title: safeTitle, contentMd: content });
  await indexNoteChunks(ctx, id, content);
  return { id };
}

export async function updateNote({ id, patch_md, position }: UpdateNoteInput, client?: DbClient) {
  const ctx = getClient(client);
  const current = await ctx.query.notes.findFirst({
    where: eq(notes.id, id),
    columns: { contentMd: true }
  });
  if (!current) throw new Error(`Note ${id} not found`);
  const merged =
    position === "append"
      ? `${current.contentMd}\n\n${patch_md}`
      : `${patch_md}\n\n${current.contentMd}`;

  await ctx
    .update(notes)
    .set({ contentMd: merged, updatedAt: new Date() })
    .where(eq(notes.id, id));
  await indexNoteChunks(ctx, id, merged);
  return { id, mergedContent: merged };
}

export async function addLink({ from_id, to_title, reason, confidence }: AddLinkInput, client?: DbClient) {
  const ctx = getClient(client);
  const target = await ctx.execute(
    sql`SELECT id FROM notes WHERE lower(title) = lower(${to_title}) ORDER BY updated_at DESC LIMIT 1`
  );
  const row = Array.isArray(target.rows) ? target.rows[0] : undefined;
  if (!row?.id) {
    return { created: false, reason: "target_not_found" as const };
  }

  await ctx
    .insert(noteLinks)
    .values({
      id: uuid(),
      fromId: from_id,
      toId: row.id as string,
      reason,
      confidence
    })
    .onConflictDoNothing();

  return { created: true, to_id: row.id as string };
}

export async function addTag({ note_id, tag, weight = 1 }: AddTagInput, client?: DbClient) {
  const ctx = getClient(client);
  await ctx
    .insert(noteTags)
    .values({ noteId: note_id, tag, weight })
    .onConflictDoUpdate({
      target: [noteTags.noteId, noteTags.tag],
      set: {
        weight: sql`${noteTags.weight} + ${weight}`
      }
    });
}

export async function addSource({ note_id, source }: AddSourceInput, client?: DbClient) {
  const ctx = getClient(client);
  const publishedAt = source.published_at ? new Date(source.published_at) : null;

  const existing = await ctx.query.sources.findFirst({
    where: eq(sources.url, source.url),
    columns: { id: true }
  });

  let sourceId: string;

  if (existing) {
    sourceId = existing.id;
    await ctx
      .update(sources)
      .set({
        title: source.title,
        domain: source.domain,
        summary: source.summary,
        publishedAt
      })
      .where(eq(sources.id, sourceId));
  } else {
    const inserted = await ctx
      .insert(sources)
      .values({
        id: uuid(),
        url: source.url,
        domain: source.domain,
        title: source.title,
        publishedAt,
        summary: source.summary
      })
      .returning({ id: sources.id });

    sourceId = inserted[0]?.id ?? (await ctx.query.sources.findFirst({
      where: eq(sources.url, source.url),
      columns: { id: true }
    }))?.id ?? uuid();
  }

  await ctx
    .insert(noteSources)
    .values({ noteId: note_id, sourceId, relevance: 1 })
    .onConflictDoNothing();

  return { source_id: sourceId };
}

async function indexNoteChunks(client: DbClient, noteId: string, content: string) {
  await reindexNoteWithClient(client, noteId, content);
}

export async function findNoteByTitle(title: string, client?: DbClient) {
  const ctx = getClient(client);
  const res = await ctx.execute(
    sql`SELECT id, title FROM notes WHERE lower(title) = lower(${title}) ORDER BY updated_at DESC LIMIT 1`
  );
  const row = Array.isArray(res.rows) ? res.rows[0] : undefined;
  return row ? { id: row.id as string, title: row.title as string } : null;
}

export async function noteExists(id: string, client?: DbClient) {
  const ctx = getClient(client);
  const item = await ctx.query.notes.findFirst({ where: eq(notes.id, id), columns: { id: true } });
  return Boolean(item);
}
