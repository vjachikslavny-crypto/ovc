type TavilySearchResponse = {
  results?: Array<{
    title?: string;
    url: string;
    content?: string;
    snippet?: string;
    description?: string;
    score?: number;
    published_date?: string | null;
    image_url?: string | null;
    metadata?: Record<string, unknown>;
  }>;
  images?: Array<{
    url: string;
    description?: string;
  }>;
};

export type WebSearchItem = {
  url: string;
  title: string;
  domain: string;
  summary: string;
  published_at: string | null;
  score?: number;
  image_url?: string | null;
  content?: string;
  language: string;
};

const FALLBACK_HOSTNAME = "example.com";

type TavilyOptions = {
  language?: string;
  languages?: string[];
};

export async function tavilySearch(query: string, maxResults = 2, options: TavilyOptions = {}): Promise<WebSearchItem[]> {
  const apiKey = process.env.TAVILY_API_KEY;
  if (!apiKey) {
    console.warn("TAVILY_API_KEY is not set; returning empty search results.");
    return [];
  }
  const languages = (options.languages?.length
    ? options.languages
    : [options.language || "ru"]).filter(Boolean);
  const uniqueLanguages = Array.from(new Set(languages));
  if (uniqueLanguages.length === 0) {
    uniqueLanguages.push("ru");
  }

  const aggregated: WebSearchItem[] = [];
  const seen = new Set<string>();
  const languageQuotas = new Map<string, number>();
  const totalLanguages = uniqueLanguages.length;
  const baseQuota = Math.max(1, Math.floor(maxResults / totalLanguages));
  const remainder = Math.max(0, maxResults - baseQuota * totalLanguages);

  uniqueLanguages.forEach((lang, index) => {
    languageQuotas.set(lang, baseQuota + (index < remainder ? 1 : 0));
  });

  for (const lang of uniqueLanguages) {
    if (aggregated.length >= maxResults) break;

    let response: Response;
    try {
      response = await fetch("https://api.tavily.com/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          api_key: apiKey,
          query,
          max_results: Math.max(1, Math.min(maxResults, 8)),
          search_depth: "basic",
          include_answer: false,
          include_images: true,
          include_results: true,
          search_lang: lang,
          result_lang: lang
        })
      });
    } catch (error) {
      console.warn("Tavily request failed", error);
      continue;
    }

    if (!response) {
      console.warn("Tavily search skipped: no response", lang);
      continue;
    }

    if (!response.ok) {
      console.warn("Tavily search failed", response.status, response.statusText);
      continue;
    }

    let data: TavilySearchResponse | null = null;
    try {
      data = (await response.json()) as TavilySearchResponse;
    } catch (error) {
      console.warn("Tavily response parse failed", error);
      continue;
    }
    const results = data?.results ?? [];

    const imageCandidates = new Map<string, string>();
    data.images?.forEach((image) => {
      if (image.url) {
        imageCandidates.set(image.url, image.description ?? "");
      }
    });

    let addedForLanguage = 0;
    const quota = languageQuotas.get(lang) ?? 1;

    for (const item of results) {
      if (!item.url || seen.has(item.url)) continue;
      if (addedForLanguage >= quota) break;

      let domain: string;
      try {
        domain = new URL(item.url).hostname;
      } catch {
        domain = FALLBACK_HOSTNAME;
      }

      const snippet = item.content?.trim() || item.snippet?.trim() || item.description?.trim() || "";
      let imageUrl: string | null = null;

      if (typeof item.image_url === "string" && item.image_url) {
        imageUrl = item.image_url;
      } else if (item.metadata && typeof item.metadata === "object") {
        const metaImage =
          (item.metadata as { image_url?: string; image?: string }).image_url ||
          (item.metadata as { image_url?: string; image?: string }).image;
        if (metaImage) {
          imageUrl = metaImage;
        }
      }
      if (!imageUrl) {
        for (const key of imageCandidates.keys()) {
          imageUrl = key;
          break;
        }
      }

      aggregated.push({
        url: item.url,
        title: item.title?.trim() || domain,
        domain,
        summary: snippet,
        content: snippet,
        published_at: item.published_date ?? null,
        score: item.score,
        image_url: imageUrl ?? null,
        language: lang
      });
      seen.add(item.url);
      addedForLanguage += 1;
      if (aggregated.length >= maxResults) break;
    }
  }

  return aggregated.slice(0, maxResults);
}
