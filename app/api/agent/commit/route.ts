import { NextResponse } from "next/server";
import { z } from "zod";
import { draftActionSchema } from "@/lib/actions";
import { commitDraft } from "@/server/agent/commitDraft";
import { db } from "@/lib/db";
import { messages } from "@/lib/schema";

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

  const result = await commitDraft(draft, { userId: "demo" });

  await db.insert(messages).values({
    role: "agent",
    text: `Готово! Применил ${result.applied} изменений.`,
    meta: {
      notes: result.notesChanged,
      applied: result.applied
    }
  });

  return NextResponse.json(result);
}
