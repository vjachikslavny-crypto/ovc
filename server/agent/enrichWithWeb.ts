import type { DraftAction } from "@/types/agent";
import type { WebItem } from "@/types/web";
import { createWebProvider } from "@/server/providers/web";

const webProvider = createWebProvider();

export async function enrichWithWeb(
  noteId: string,
  topic: string,
  languages?: string[]
): Promise<{ actions: DraftAction[]; items: WebItem[] }> {
  const items = await webProvider.search({ query: topic, languages });
  if (items.length === 0) {
    return { actions: [], items: [] };
  }

  const selected = pickPerLanguage(items, languages);
  if (selected.length === 0) {
    return { actions: [], items: [] };
  }

  const lines = selected.map((item) => {
    const date = item.published_at ? ` (${item.published_at})` : "";
    return `- [${item.title}](${item.url}) — ${item.summary ?? "Краткие факты"}${date}`;
  });

  const updateAction: DraftAction = {
    type: "update_note",
    id: noteId,
    patch_md: `## Информация из интернета\n${lines.join("\n")}`,
    position: "append"
  };

  const sourceActions: DraftAction[] = selected.map((item) => ({
    type: "add_source",
    note_id: noteId,
    source: {
      url: item.url,
      title: item.title,
      domain: item.domain,
      published_at: item.published_at ?? new Date().toISOString().slice(0, 10),
      summary: item.summary ?? ""
    }
  }));

  return {
    actions: [updateAction, ...sourceActions],
    items: selected
  };
}

function pickPerLanguage(items: WebItem[], languages?: string[]) {
  if (items.length <= 1) return items.slice(0, 1);

  const normalizedUrls = new Set<string>();
  const deduped: WebItem[] = [];
  for (const item of items) {
    const key = item.url.trim();
    if (normalizedUrls.has(key)) continue;
    normalizedUrls.add(key);
    deduped.push(item);
  }

  const requested = (languages ?? []).map((lang) => lang.toLowerCase());
  const max = requested.length > 0 ? requested.length : 1;
  const picked: WebItem[] = [];
  const usedIndices = new Set<number>();
  const seenLanguages = new Set<string>();

  const register = (item: WebItem, index: number) => {
    usedIndices.add(index);
    const lang = (item.language ?? "").toLowerCase();
    if (lang) {
      seenLanguages.add(lang);
    }
    picked.push(item);
  };

  if (requested.length > 0) {
    requested.forEach((lang) => {
      if (picked.length >= max) return;
      const index = deduped.findIndex((item, idx) => {
        if (usedIndices.has(idx)) return false;
        return (item.language ?? "").toLowerCase() === lang;
      });
      if (index !== -1) {
        register(deduped[index], index);
      }
    });
  }

  for (let i = 0; i < deduped.length && picked.length < max; i += 1) {
    if (usedIndices.has(i)) continue;
    const lang = (deduped[i].language ?? "").toLowerCase();
    if (lang && seenLanguages.has(lang)) continue;
    register(deduped[i], i);
  }

  if (picked.length === 0 && deduped.length > 0) {
    register(deduped[0], 0);
  }

  return picked;
}
