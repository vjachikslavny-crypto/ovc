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
  searchLanguages: string[];
  toggleSearchLanguage: (language: string) => void;
  sendMessage: (text: string, noteId?: string) => Promise<void>;
  applyDraft: () => Promise<void>;
  resetDraft: () => void;
};

const LANGUAGE_STORAGE_KEY = "ovc-search-languages";

function loadLanguages(): string[] {
  if (typeof window === "undefined") return ["ru"];
  try {
    const raw = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (!raw) return ["ru"];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed.filter((item) => typeof item === "string" && item.length >= 2) as string[];
    }
  } catch (error) {
    console.warn("Failed to parse saved languages", error);
  }
  return ["ru"];
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  draft: [],
  isSending: false,
  error: undefined,
  searchLanguages: loadLanguages(),
  toggleSearchLanguage(language: string) {
    set((state) => {
      const hasLanguage = state.searchLanguages.includes(language);
      let next: string[];
      if (hasLanguage) {
        next = state.searchLanguages.filter((item) => item !== language);
        if (next.length === 0) {
          next = ["ru"];
        }
      } else {
        next = [...state.searchLanguages, language];
      }
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LANGUAGE_STORAGE_KEY, JSON.stringify(next));
      }
      return { searchLanguages: next };
    });
  },
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
        body: JSON.stringify({
          text,
          noteId,
          languages: get().searchLanguages
        })
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
