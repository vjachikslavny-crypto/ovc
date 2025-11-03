import { NextResponse } from "next/server";
import { z } from "zod";
import { ragSearch } from "@/lib/rag";

const searchSchema = z.object({
  query: z.string().min(1),
  k: z.number().min(1).max(20).optional()
});

export async function POST(request: Request) {
  const payload = await request.json().catch(() => null);
  const parsed = searchSchema.safeParse(payload);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid query", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { query, k } = parsed.data;
  const results = await ragSearch(query, k ?? 5);
  return NextResponse.json({ results });
}
