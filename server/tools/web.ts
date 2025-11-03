import { tavilySearch } from "@/server/web/tavily";
import type { WebItem } from "@/types/web";

type WebSearchInput = {
  q: string;
  languages?: string[];
};

const demoItems: WebItem[] = [
  {
    url: "https://example.com/a",
    title: "Demo Source A",
    domain: "example.com",
    published_at: "2025-01-10",
    summary: "3–5 фактов по теме A"
  },
  {
    url: "https://example.com/b",
    title: "Demo Source B",
    domain: "example.com",
    published_at: "2025-02-03",
    summary: "Короткий вывод B"
  }
];

const webEnabled = process.env.WEB_ENABLE !== "false";

export async function webSearch({ q, languages }: WebSearchInput) {
  if (!webEnabled) {
    return { items: demoItems };
  }

  const maxResults = Number(process.env.WEB_MAX_RESULTS ?? 8);
  const results = await tavilySearch(q, maxResults, { languages });
  if (results.length === 0) {
    return { items: demoItems };
  }

  const items: WebItem[] = results.map((item) => ({
    url: item.url,
    title: item.title,
    domain: item.domain,
    published_at: item.published_at ?? new Date().toISOString().slice(0, 10),
    summary: item.summary
  }));

  return { items };
}
