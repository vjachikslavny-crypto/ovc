"use client";

import { FormEvent, useState } from "react";

type SearchResult = {
  noteId: string;
  chunkId: string;
  text: string;
  score: number;
};

export function NoteSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    setError(null);
    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });
      if (!response.ok) {
        throw new Error("Поиск недоступен");
      }
      const data = await response.json();
      setResults(data.results ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка поиска");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Например: pgvector ембеддинги"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
        />
        <button
          type="submit"
          disabled={isSearching}
          className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        >
          {isSearching ? "Ищем..." : "Искать"}
        </button>
      </form>
      {error && <span className="text-sm text-red-600">{error}</span>}
      {results.length > 0 && (
        <ul className="flex flex-col gap-3">
          {results.map((item) => (
            <li key={item.chunkId} className="rounded-md border border-gray-100 p-3">
              <div className="flex items-center justify-between text-xs text-gray-500">
                <a
                  href={`/n/${item.noteId}`}
                  className="font-medium text-blue-600 hover:text-blue-800"
                >
                  Перейти к заметке
                </a>
                <span>{(item.score * 100).toFixed(1)}%</span>
              </div>
              <p className="mt-2 text-sm text-gray-700">{item.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
