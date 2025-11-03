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
  draftSelection: Record<string, boolean>;
  isSending: boolean;
  error?: string;
  searchLanguages: string[];
  toggleSearchLanguage: (language: string) => void;
  toggleDraftAction: (key: string) => void;
  setAllDraftSelection: (value: boolean) => void;
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
  draftSelection: {},
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
  toggleDraftAction(key: string) {
    set((state) => ({
      draftSelection: {
        ...state.draftSelection,
        [key]: !state.draftSelection[key]
      }
    }));
  },
  setAllDraftSelection(value: boolean) {
    set((state) => ({
      draftSelection: buildSelectionMap(state.draft, value)
    }));
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
      const data: { reply: string; draft?: DraftAction[] } = await response.json();
      set((state) => ({
        messages: [
          ...state.messages,
          { id: crypto.randomUUID(), role: "agent", text: data.reply }
        ],
        draft: data.draft ?? [],
        draftSelection: buildSelectionMap(data.draft ?? [], true),
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
    const { draft, draftSelection } = get();
    const selected = draft.filter((action) => draftSelection[actionKey(action)]);
    if (selected.length === 0) return;
    set({ isSending: true, error: undefined });
    try {
      const response = await fetch("/api/agent/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft: selected })
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
        draftSelection: {},
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
    set({ draft: [], draftSelection: {} });
  }
}));

function actionKey(action: DraftAction) {
  return JSON.stringify(action);
}

function buildSelectionMap(actions: DraftAction[], value = true) {
  const map: Record<string, boolean> = {};
  actions.forEach((action) => {
    map[actionKey(action)] = value;
  });
  return map;
}

export const draftActionKey = actionKey;
