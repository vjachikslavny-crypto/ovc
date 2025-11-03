import type { WebItem } from "@/types/web";
import { TavilyWebProvider } from "./tavily";

export interface WebSearchParams {
  query: string;
  languages?: string[];
}

export interface WebProvider {
  search(params: WebSearchParams): Promise<WebItem[]>;
}

export function createWebProvider(): WebProvider {
  const provider = (process.env.WEB_PROVIDER || "tavily").toLowerCase();
  switch (provider) {
    case "tavily":
    default:
      return new TavilyWebProvider();
  }
}
