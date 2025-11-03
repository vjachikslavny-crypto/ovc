const DEFAULT_DIM = Number(process.env.VECTOR_DIM || 384);

export interface EmbeddingsProvider {
  embed(input: string[]): Promise<number[][]>;
}

class LocalRandomEmbeddings implements EmbeddingsProvider {
  private readonly dim: number;

  constructor(dim = DEFAULT_DIM) {
    this.dim = dim;
  }

  async embed(input: string[]): Promise<number[][]> {
    return input.map((text) => this.generateVector(text));
  }

  private generateVector(text: string): number[] {
    const seed = hashString(text);
    const generator = mulberry32(seed);
    const vector: number[] = [];
    for (let i = 0; i < this.dim; i += 1) {
      vector.push(generator() * 2 - 1);
    }
    return normalize(vector);
  }
}

export const embeddings: EmbeddingsProvider = new LocalRandomEmbeddings();

function hashString(text: string) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }
  return hash >>> 0;
}

function mulberry32(seed: number) {
  let t = seed;
  return () => {
    t += 0x6d2b79f5;
    let x = t;
    x = Math.imul(x ^ (x >>> 15), x | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function normalize(vector: number[]) {
  const length = Math.sqrt(vector.reduce((acc, value) => acc + value * value, 0));
  if (length === 0) return vector;
  return vector.map((value) => value / length);
}
