import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/lib/db";
import { draftActions, messages, notes } from "@/lib/schema";
import { planAndDraftActions } from "@/server/agent";

const messageSchema = z.object({
  text: z.string().min(1),
  noteId: z.string().uuid().optional()
});

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parse = messageSchema.safeParse(body);

  if (!parse.success) {
    return NextResponse.json(
      { error: "Invalid payload", details: parse.error.flatten() },
      { status: 400 }
    );
  }

  const { text, noteId } = parse.data;
  const noteList = await db
    .select({
      id: notes.id,
      title: notes.title,
      contentMd: notes.contentMd
    })
    .from(notes);

  const result = await planAndDraftActions(text, {
    notes: noteList,
    noteId
  });

  await db.insert(messages).values([
    {
      role: "user",
      text,
      meta: { noteId }
    },
    {
      role: "agent",
      text: result.reply,
      meta: {
        draftSize: result.draft.length,
        draftActions: result.draft,
        noteId
      }
    }
  ]);

  await db.insert(draftActions).values({
    payload: result.draft
  });

  return NextResponse.json(result);
}
