import { NextResponse } from "next/server";
import { z } from "zod";
import { tavilySearch } from "@/server/web/tavily";

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
  const normalized = q.trim();

  const results = normalized ? await tavilySearch(normalized) : [];

  return NextResponse.json({
    items: results
  });
}
