import { NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { z } from "zod";
import { db } from "@/lib/db";
import { notes } from "@/lib/schema";
import { reindexNote, createWikiLinks, createSemanticLinks } from "@/lib/rag";

const updateNoteSchema = z.object({
  title: z.string().min(1, "Название не может быть пустым"),
  content_md: z.string().min(1, "Содержимое не может быть пустым")
});

type RouteContext = {
  params: { id: string };
};

export async function PATCH(request: Request, { params }: RouteContext) {
  const payload = await request.json().catch(() => null);
  const parsed = updateNoteSchema.safeParse(payload);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Некорректные данные", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { id } = params;
  if (!id) {
    return NextResponse.json({ error: "Не указан идентификатор заметки" }, { status: 400 });
  }

  const { title, content_md: contentMd } = parsed.data;

  const existing = await db
    .select({ id: notes.id })
    .from(notes)
    .where(eq(notes.id, id))
    .limit(1);
  if (existing.length === 0) {
    return NextResponse.json({ error: "Заметка не найдена" }, { status: 404 });
  }

  await db
    .update(notes)
    .set({
      title,
      contentMd,
      updatedAt: new Date()
    })
    .where(eq(notes.id, id));

  await reindexNote(id, contentMd);
  await createWikiLinks(id, contentMd);
  await createSemanticLinks(id);

  return NextResponse.json({ ok: true });
}
