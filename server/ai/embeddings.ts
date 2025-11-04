import type { Embedder } from "@/server/providers/llm";
import { getEmbedder } from "@/server/providers/llm";

export interface EmbeddingsProvider {
  embed(input: string[]): Promise<number[][]>;
}

const provider: Embedder = getEmbedder();

export const embeddings: EmbeddingsProvider = {
  embed(input: string[]) {
    return provider.embed(input);
  }
};
