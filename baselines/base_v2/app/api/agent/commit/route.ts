import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/lib/db";
import {
  draftActions,
  messages,
  noteLinks,
  noteSources,
  noteTags,
  notes,
  sources
} from "@/lib/schema";
import { draftActionSchema } from "@/lib/actions";
import { eq, and } from "drizzle-orm";
import { reindexNote, createWikiLinks, createSemanticLinks } from "@/lib/rag";
import { plainTextPreview } from "@/lib/markdown";

const commitSchema = z.object({
  draft: z.array(draftActionSchema)
});

export async function POST(request: Request) {
  const payload = await request.json().catch(() => null);
  const parsed = commitSchema.safeParse(payload);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid draft payload", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { draft } = parsed.data;
  if (draft.length === 0) {
    return NextResponse.json({ applied: 0, notesChanged: [] });
  }

  const updatedContent = new Map<string, string>();
  const touchedNotes = new Set<string>();
  let applied = 0;

  await db.transaction(async (tx) => {
    for (const action of draft) {
      switch (action.type) {
        case "create_note": {
          const [created] = await tx
            .insert(notes)
            .values({
              title: action.title,
              contentMd: action.content_md
            })
            .returning({ id: notes.id, contentMd: notes.contentMd });
          if (created) {
            updatedContent.set(created.id, created.contentMd);
            touchedNotes.add(created.id);
            applied += 1;
          }
          break;
        }
        case "update_note": {
          const existing = await tx
            .select({
              id: notes.id,
              contentMd: notes.contentMd
            })
            .from(notes)
            .where(eq(notes.id, action.id))
            .limit(1);
          const current = existing[0];
          if (!current) break;
          const nextContent =
            action.position === "prepend"
              ? `${action.patch_md}\n\n${current.contentMd}`
              : `${current.contentMd}\n\n${action.patch_md}`;
          await tx
            .update(notes)
            .set({
              contentMd: nextContent,
              updatedAt: new Date()
            })
            .where(eq(notes.id, action.id));
          updatedContent.set(action.id, nextContent);
          touchedNotes.add(action.id);
          applied += 1;
          break;
        }
        case "add_link": {
          const target = await tx
            .select({ id: notes.id })
            .from(notes)
            .where(eq(notes.title, action.to_title))
            .limit(1);
          const match = target[0];
          if (!match) break;
          const existing = await tx
            .select({ id: noteLinks.id })
            .from(noteLinks)
            .where(
              and(
                eq(noteLinks.fromId, action.from_id),
                eq(noteLinks.toId, match.id),
                eq(noteLinks.reason, action.reason)
              )
            )
            .limit(1);
          if (existing.length === 0) {
            await tx.insert(noteLinks).values({
              fromId: action.from_id,
              toId: match.id,
              reason: action.reason,
              confidence: action.confidence
            });
            touchedNotes.add(action.from_id);
            touchedNotes.add(match.id);
            applied += 1;
          }
          break;
        }
        case "add_source": {
          const existingSource = await tx
            .select({ id: sources.id })
            .from(sources)
            .where(eq(sources.url, action.source.url))
            .limit(1);
          const sourceId =
            existingSource[0]?.id ??
            (
              await tx
                .insert(sources)
                .values({
                  url: action.source.url,
                  domain: action.source.domain,
                  title: action.source.title,
                  publishedAt: action.source.published_at,
                  summary: action.source.summary
                })
                .returning({ id: sources.id })
            )[0]?.id;
          if (sourceId) {
            await tx.insert(noteSources).values({
              noteId: action.note_id,
              sourceId,
              relevance: 0.9
            });
            touchedNotes.add(action.note_id);
            applied += 1;
          }
          break;
        }
        case "add_tag": {
          await tx.insert(noteTags).values({
            noteId: action.note_id,
            tag: action.tag,
            weight: action.weight ?? 1
          });
          touchedNotes.add(action.note_id);
          applied += 1;
          break;
        }
        default:
          break;
      }
    }
  });

  for (const [noteId, content] of updatedContent.entries()) {
    await reindexNote(noteId, content);
    await createWikiLinks(noteId, content);
    await createSemanticLinks(noteId);
  }

  if (applied > 0) {
    await db.insert(messages).values({
      role: "agent",
      text: `Готово! Применил ${applied} изменений.`,
      meta: {
        notes: Array.from(touchedNotes),
        applied,
        updatedContent: Array.from(updatedContent.entries()).map(([id, content]) => ({
          id,
          preview: plainTextPreview(content, 160)
        }))
      }
    });
  }

  await db.delete(draftActions);

  return NextResponse.json({
    applied,
    notesChanged: Array.from(touchedNotes)
  });
}
