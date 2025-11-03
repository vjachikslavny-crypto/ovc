import type { WebItem } from "@/types/web";
import type { WebProvider, WebSearchParams } from "./index";
import { tavilySearch } from "@/server/web/tavily";

export class TavilyWebProvider implements WebProvider {
  async search({ query, languages }: WebSearchParams): Promise<WebItem[]> {
    const maxResults = Math.max(languages?.length ?? 1, 1);
    const results = await tavilySearch(query, maxResults, { languages });
    return results.map((item) => ({
      url: item.url,
      title: item.title,
      domain: item.domain,
      published_at: item.published_at ?? undefined,
      summary: item.summary,
      language: item.language
    }));
  }
}
