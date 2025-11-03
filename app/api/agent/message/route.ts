import { NextResponse } from "next/server";
import { z } from "zod";
import { db } from "@/lib/db";
import { messages } from "@/lib/schema";
import { handleUserMessage } from "@/server/agent/orchestrator";

const messageSchema = z.object({
  text: z.string().min(1),
  noteId: z.string().uuid().optional(),
  language: z.string().min(2).max(5).optional(),
  languages: z.array(z.string().min(2).max(5)).min(1).optional()
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

  const { text, noteId, language, languages } = parse.data;
  const normalizedLanguages = Array.from(
    new Set(
      languages?.length
        ? languages
        : language
        ? [language]
        : []
    )
  ).filter((item) => item.length >= 2);

  try {
    const result = await handleUserMessage(text, {
      noteId,
      languages: normalizedLanguages.length > 0 ? normalizedLanguages : undefined
    });

    await db.insert(messages).values([
      {
        role: "user",
        text,
        meta: { noteId, languages: normalizedLanguages }
      },
      {
        role: "agent",
        text: result.reply,
        meta: {
          draftSize: result.draft?.length ?? 0,
          draftActions: result.draft,
          noteId
        }
      }
    ]);

    return NextResponse.json(result);
  } catch (error) {
    console.error("handleUserMessage failed", error);
    return NextResponse.json(
      { error: "Agent failed to respond" },
      { status: 500 }
    );
  }
}
