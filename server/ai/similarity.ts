export function cosineSimilarity(a: number[], b: number[]) {
  const length = Math.min(a.length, b.length);
  if (length === 0) return 0;
  let dot = 0;
  let magA = 0;
  let magB = 0;

  for (let i = 0; i < length; i += 1) {
    const va = a[i] ?? 0;
    const vb = b[i] ?? 0;
    dot += va * vb;
    magA += va * va;
    magB += vb * vb;
  }

  if (magA === 0 || magB === 0) return 0;
  return dot / Math.sqrt(magA * magB);
}

export function knn<T>(
  query: number[],
  items: T[],
  getVector: (item: T) => number[],
  limit = 5
) {
  return items
    .map((item) => ({
      item,
      score: cosineSimilarity(query, getVector(item))
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}
