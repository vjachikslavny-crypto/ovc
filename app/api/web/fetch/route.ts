import { NextResponse } from "next/server";
import { z } from "zod";

const fetchSchema = z.object({
  url: z.string().url()
});

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = fetchSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid payload", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { url } = parsed.data;
  const domain = new URL(url).hostname;
  const today = new Date().toISOString().slice(0, 10);

  return NextResponse.json({
    title: `Сводка по ${domain}`,
    domain,
    published_at: today,
    summary: `Это демо-ответ, показывающий как может выглядеть выжимка для ${url}.`
  });
}
