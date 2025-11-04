export interface LLM {
  chat(prompt: string, systemPrompt?: string): Promise<string>;
}

export interface Embedder {
  embed(texts: string[]): Promise<number[][]>;
}

export function getLLM(): LLM {
  const provider = (process.env.LLM_PROVIDER || "mock").toLowerCase();
  switch (provider) {
    case "ollama":
      return require("./ollama").llm as LLM;
    case "mock":
    default:
      return require("./mock").llm as LLM;
  }
}

export function getEmbedder(): Embedder {
  const provider = (process.env.EMBEDDINGS_PROVIDER || "mock").toLowerCase();
  switch (provider) {
    case "ollama":
      return require("./ollama").embedder as Embedder;
    case "mock":
    default:
      return require("./mock").embedder as Embedder;
  }
}
