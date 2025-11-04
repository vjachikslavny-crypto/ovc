import crypto from "crypto";
import type { LLM, Embedder } from "./index";

export const llm: LLM = {
  async chat(prompt: string, systemPrompt?: string) {
    const hash = crypto
      .createHash("sha256")
      .update(`${systemPrompt ?? ""}::${prompt}`)
      .digest("hex")
      .slice(0, 8);
    return `Mock reply (${hash}): черновик действий сформирован локально.`;
  }
};

export const embedder: Embedder = {
  async embed(texts: string[]) {
    const dim = Number(process.env.VECTOR_DIM ?? 384);
    return texts.map((text) => {
      const seed = crypto.createHash("sha256").update(text).digest();
      const vector = new Array<number>(dim);
      for (let i = 0; i < dim; i += 1) {
        const raw = seed[i % seed.length];
        vector[i] = (raw / 255) * 2 - 1;
      }
      return vector;
    });
  }
};
