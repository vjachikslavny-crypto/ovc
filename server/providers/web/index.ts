export type WebItem = {
  url: string;
  title: string;
  domain: string;
  published_at?: string;
  summary?: string;
};

export async function webSearch(_: { q: string }): Promise<{ items: WebItem[] }> {
  return { items: [] };
}
