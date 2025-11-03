/* eslint-disable react/no-array-index-key */
"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useChatStore, draftActionKey } from "@/stores/chat-store";
import { DiffCard } from "./DiffCard";
import { Bot, User } from "lucide-react";

type ChatViewProps = {
  initialMessage?: string;
  initialNoteId?: string;
};

export function ChatView({ initialMessage, initialNoteId }: ChatViewProps) {
  const [input, setInput] = useState(initialMessage ?? "");
  const [noteId, setNoteId] = useState<string | undefined>(initialNoteId);
  const {
    messages,
    draft,
    draftSelection,
    isSending,
    error,
    sendMessage,
    applyDraft,
    toggleDraftAction,
    setAllDraftSelection
  } = useChatStore();

  useEffect(() => {
    if (initialMessage) {
      setInput(initialMessage);
    }
    if (initialNoteId) {
      setNoteId(initialNoteId);
    }
  }, [initialMessage, initialNoteId]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!input.trim()) return;
    await sendMessage(input, noteId);
    setInput("");
  };

  const selectedCount = useMemo(
    () => draft.filter((action) => draftSelection[draftActionKey(action)]).length,
    [draft, draftSelection]
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        {messages.length === 0 && (
          <div className="rounded-md bg-blue-50 p-3 text-sm text-blue-700">
            Начните диалог, например: “Создай заметку Проект Авто-поиск”.
          </div>
        )}
        {messages.map((message) => (
          <div key={message.id} className="flex gap-3 rounded-md bg-gray-50 p-3">
            <div className="mt-1 text-gray-500">
              {message.role === "agent" ? <Bot size={18} /> : <User size={18} />}
            </div>
            <div>
              <div className="text-xs uppercase tracking-wide text-gray-500">
                {message.role === "agent" ? "Агент" : "Вы"}
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-gray-800">
                {message.text}
              </p>
            </div>
          </div>
        ))}
      </div>

      {draft.length > 0 && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between text-sm font-medium text-gray-700">
            <span>
              Черновик изменений ({draft.length})
              {selectedCount > 0 ? ` — выбрано ${selectedCount}` : ""}
            </span>
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                checked={draft.length > 0 && draft.every((action) => draftSelection[draftActionKey(action)])}
                onChange={(event) => setAllDraftSelection(event.target.checked)}
              />
              Выбрать все
            </label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {draft.map((action, index) => {
              const key = draftActionKey(action);
              const checked = Boolean(draftSelection[key]);
              return (
                <label
                  key={`${action.type}-${index}`}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border border-gray-200 bg-white p-3 shadow-sm hover:border-blue-200"
                >
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    checked={checked}
                    onChange={() => toggleDraftAction(key)}
                  />
                  <DiffCard action={action} />
                </label>
              );
            })}
          </div>
          <button
            type="button"
            onClick={applyDraft}
            disabled={isSending || selectedCount === 0}
            className="inline-flex w-fit items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {isSending ? "Применяем..." : "Применить выбранные"}
          </button>
        </section>
      )}

      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
      >
        {noteId && (
          <div className="text-xs text-gray-500">
            Сообщение будет связано с заметкой ID: {noteId}
          </div>
        )}
        <label htmlFor="chat-input" className="text-sm font-medium text-gray-700">
          Сообщение агенту
        </label>
        <textarea
          id="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          rows={4}
          placeholder="Напишите вопрос или задачу..."
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
        />
        <button
          type="submit"
          disabled={isSending}
          className="inline-flex w-fit items-center justify-center rounded-md bg-gray-900 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:bg-gray-400"
        >
          {isSending ? "Отправляем..." : "Отправить"}
        </button>
        {error && <div className="text-sm text-red-600">{error}</div>}
      </form>
    </div>
  );
}
