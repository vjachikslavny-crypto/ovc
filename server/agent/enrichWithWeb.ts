import type { DraftAction } from "@/types/agent";
import type { WebItem } from "@/types/web";

export async function enrichWithWeb(
  _noteId: string,
  _topic: string,
  _languages?: string[]
): Promise<{ actions: DraftAction[]; items: WebItem[] }> {
  return { actions: [], items: [] };
}
