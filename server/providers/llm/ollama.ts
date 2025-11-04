import type { LLM, Embedder } from "./index";

const BASE_URL = process.env.OLLAMA_BASE_URL || "http://localhost:11434";

export const llm: LLM = {
  async chat(prompt: string, systemPrompt?: string) {
    const payload = {
      model: process.env.OLLAMA_LLM_MODEL || "mistral:7b-instruct",
      messages: [
        systemPrompt ? { role: "system", content: systemPrompt } : null,
        { role: "user", content: prompt }
      ].filter(Boolean)
    };

    const response = await fetch(`${BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`Ollama chat error: ${response.status}`);
    }

    const json = (await response.json()) as { message?: { content?: string } };
    return json.message?.content ?? "";
  }
};

export const embedder: Embedder = {
  async embed(texts: string[]) {
    const response = await fetch(`${BASE_URL}/api/embeddings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: process.env.OLLAMA_EMBED_MODEL || "nomic-embed-text",
        input: texts
      })
    });

    if (!response.ok) {
      throw new Error(`Ollama embeddings error: ${response.status}`);
    }

    const json = (await response.json()) as { embeddings: number[][] };
    return json.embeddings;
  }
};
