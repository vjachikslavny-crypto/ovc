import { NextResponse } from "next/server";
import { z } from "zod";

const searchSchema = z.object({
  q: z.string().min(1)
});

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = searchSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid payload", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { q } = parsed.data;
  const normalized = q.trim() || "general";
  const today = new Date().toISOString().slice(0, 10);

  return NextResponse.json({
    items: [
      {
        url: `https://news.example.com/${encodeURIComponent(normalized)}`,
        title: `${normalized} — обзор свежих публикаций`,
        domain: "news.example.com",
        published_at: today,
        summary: `Собрали несколько ключевых новостей и мнений вокруг темы «${normalized}».`
      },
      {
        url: `https://blog.example.com/posts/${encodeURIComponent(normalized)}-insights`,
        title: `${normalized}: практический взгляд`,
        domain: "blog.example.com",
        published_at: today,
        summary: `Короткая выжимка из аналитических материалов и блогов, связанных с «${normalized}».`
      }
    ]
  });
}
