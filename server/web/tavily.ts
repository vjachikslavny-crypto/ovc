/**
 * Tavily search integration - offline stub
 * В офлайн-режиме возвращает пустые результаты
 * Для будущей интеграции можно заменить на реальный API или локальную нейросеть
 */

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

type TavilyOptions = {
  language?: string;
  languages?: string[];
};

/**
 * Заглушка для Tavily поиска в офлайн-режиме
 * В будущем можно заменить на локальную нейросеть или реальный API
 */
export async function tavilySearch(
  query: string,
  maxResults = 2,
  options: TavilyOptions = {}
): Promise<WebSearchItem[]> {
  const offlineMode = process.env.OFFLINE_MODE === "true";
  const apiKey = process.env.TAVILY_API_KEY;

  // В офлайн-режиме или без API ключа возвращаем пустой результат
  if (offlineMode || !apiKey) {
    if (process.env.NODE_ENV !== "production") {
      console.log(
        `[Tavily stub] Web search disabled (OFFLINE_MODE=${offlineMode}, API_KEY=${!!apiKey}). Query: "${query}"`
      );
    }
    return [];
  }

  // Если есть API ключ, но пользователь хочет использовать реальный поиск в будущем
  // Здесь можно добавить реальный вызов Tavily API
  // Пока возвращаем пустой массив для офлайн-режима

  return [];
}

