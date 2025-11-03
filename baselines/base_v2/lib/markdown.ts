const DEFAULT_CHUNK_SIZE = 800;
const DEFAULT_CHUNK_OVERLAP = 100;

export function chunkMarkdown(
  markdown: string,
  chunkSize = DEFAULT_CHUNK_SIZE,
  overlap = DEFAULT_CHUNK_OVERLAP
) {
  const cleaned = markdown.trim();
  if (!cleaned) return [];

  const chunks: string[] = [];
  let start = 0;

  while (start < cleaned.length) {
    const end = Math.min(start + chunkSize, cleaned.length);
    const chunk = cleaned.slice(start, end);
    chunks.push(chunk);
    if (end === cleaned.length) break;
    start = Math.max(0, end - overlap);
  }

  return chunks;
}

export function plainTextPreview(markdown: string, limit = 180) {
  const text = markdown.replace(/[#>*_`]/g, "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}
