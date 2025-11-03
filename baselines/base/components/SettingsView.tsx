"use client";

import { useState } from "react";

export function SettingsView() {
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

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
    <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
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
