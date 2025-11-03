import { create } from "zustand";
import type { DraftAction } from "@/lib/actions";

export type ChatMessage = {
  id: string;
  role: "user" | "agent";
  text: string;
  meta?: Record<string, unknown>;
};

type ChatState = {
  messages: ChatMessage[];
  draft: DraftAction[];
  isSending: boolean;
  error?: string;
  sendMessage: (text: string, noteId?: string) => Promise<void>;
  applyDraft: () => Promise<void>;
  resetDraft: () => void;
};

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  draft: [],
  isSending: false,
  error: undefined,
  async sendMessage(text: string, noteId?: string) {
    if (!text.trim()) return;
    const tempId = crypto.randomUUID();
    set((state) => ({
      messages: [
        ...state.messages,
        { id: tempId, role: "user", text, meta: noteId ? { noteId } : undefined }
      ],
      isSending: true,
      error: undefined
    }));

    try {
      const response = await fetch("/api/agent/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, noteId })
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error?.error ?? "Не удалось получить ответ агента");
      }
      const data: { reply: string; draft: DraftAction[] } = await response.json();
      set((state) => ({
        messages: [
          ...state.messages,
          { id: crypto.randomUUID(), role: "agent", text: data.reply }
        ],
        draft: data.draft,
        isSending: false
      }));
    } catch (error) {
      set((state) => ({
        isSending: false,
        error: error instanceof Error ? error.message : "Неизвестная ошибка",
        messages: state.messages
      }));
    }
  },
  async applyDraft() {
    const { draft } = get();
    if (draft.length === 0) return;
    set({ isSending: true, error: undefined });
    try {
      const response = await fetch("/api/agent/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft })
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error?.error ?? "Коммит не удался");
      }
      const data: { applied: number; notesChanged: string[] } = await response.json();
      set((state) => ({
        messages: [
          ...state.messages,
          {
            id: crypto.randomUUID(),
            role: "agent",
            text: `Изменения применены. Обновлено заметок: ${data.notesChanged.length}.`
          }
        ],
        draft: [],
        isSending: false
      }));
    } catch (error) {
      set({
        isSending: false,
        error: error instanceof Error ? error.message : "Неизвестная ошибка"
      });
    }
  },
  resetDraft() {
    set({ draft: [] });
  }
}));
