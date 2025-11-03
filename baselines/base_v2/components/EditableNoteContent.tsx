"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { MarkdownView } from "./MarkdownView";

type EditableNoteContentProps = {
  noteId: string;
  initialTitle: string;
  initialContent: string;
  updatedAt: string;
};

export function EditableNoteContent({
  noteId,
  initialTitle,
  initialContent,
  updatedAt
}: EditableNoteContentProps) {
  const router = useRouter();
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(initialTitle);
  const [content, setContent] = useState(initialContent);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const resetChanges = () => {
    setTitle(initialTitle);
    setContent(initialContent);
    setError(null);
  };

  const handleSave = () => {
    setError(null);
    startTransition(async () => {
      try {
        const response = await fetch(`/api/notes/${noteId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, content_md: content })
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload?.error || "Не удалось сохранить изменения");
        }

        setIsEditing(false);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Неизвестная ошибка");
      }
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex-1">
          {isEditing ? (
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-lg font-semibold text-gray-800 focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
            />
          ) : (
            <h2 className="text-2xl font-semibold text-gray-800">{title}</h2>
          )}
          <span className="text-xs text-gray-500">Обновлено {new Date(updatedAt).toLocaleString()}</span>
        </div>
        <div className="flex gap-2">
          {isEditing ? (
            <>
              <button
                type="button"
                onClick={handleSave}
                disabled={isPending || title.trim().length === 0}
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
              >
                {isPending ? "Сохраняю..." : "Сохранить"}
              </button>
              <button
                type="button"
                onClick={() => {
                  resetChanges();
                  setIsEditing(false);
                }}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100"
              >
                Отмена
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setIsEditing(true)}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100"
            >
              Редактировать
            </button>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        {isEditing ? (
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={18}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
            placeholder="Напишите содержание заметки в Markdown. Можно вставлять изображения через ![alt](https://...)."
          />
        ) : (
          <MarkdownView content={content} />
        )}
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}
    </div>
  );
}
