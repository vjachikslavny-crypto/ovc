"use client";

import { useState } from "react";
import { useChatStore } from "@/stores/chat-store";

export function SettingsView() {
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const searchLanguages = useChatStore((state) => state.searchLanguages);
  const toggleSearchLanguage = useChatStore((state) => state.toggleSearchLanguage);

  const languageOptions = [
    { code: "ru", label: "Русский" },
    { code: "en", label: "English" },
    { code: "es", label: "Español" },
    { code: "de", label: "Deutsch" },
    { code: "fr", label: "Français" }
  ];

  const handleSeedReminder = async () => {
    setIsLoading(true);
    setStatus(null);
    try {
      const response = await fetch("/api/reminders/seed", { method: "POST" });
      if (!response.ok) {
        throw new Error("Не удалось создать напоминание");
      }
      const data = await response.json();
      setStatus(data.message ?? "Напоминание готово");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Ошибка при создании");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Поиск в интернете</h2>
        <p className="text-sm text-gray-600">
          Выберите языки, на которых Tavily будет искать информацию. Минимум один язык всегда активен.
        </p>
        <div className="mt-2 flex flex-col gap-2">
          {languageOptions.map((option) => {
            const checked = searchLanguages.includes(option.code);
            return (
              <label key={option.code} className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  checked={checked}
                  onChange={() => toggleSearchLanguage(option.code)}
                />
                {option.label}
              </label>
            );
          })}
        </div>
      </div>
      <div>
        <h2 className="text-lg font-semibold text-gray-800">Демо-напоминания</h2>
        <p className="text-sm text-gray-600">
          Сгенерируйте пример напоминания, чтобы посмотреть, как агент может
          напоминать о задачах (будущий Telegram-бот).
        </p>
      </div>
      <button
        type="button"
        onClick={handleSeedReminder}
        disabled={isLoading}
        className="inline-flex w-fit items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
      >
        {isLoading ? "Создаём..." : "Создать демо-напоминание"}
      </button>
      {status && <span className="text-sm text-gray-700">{status}</span>}
    </div>
  );
}
