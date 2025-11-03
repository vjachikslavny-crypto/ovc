const WIKI_PATTERN = /\[\[([^\]]+)\]\]/g;

export function extractWikiLinks(markdown: string) {
  const matches: string[] = [];
  let result: RegExpExecArray | null;
  while ((result = WIKI_PATTERN.exec(markdown)) !== null) {
    matches.push(result[1].trim());
  }
  return matches;
}
