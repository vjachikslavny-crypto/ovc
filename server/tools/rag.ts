import { ragSearch } from "@/lib/rag";

type SearchInput = {
  query: string;
  k?: number;
};

export async function search({ query, k = 8 }: SearchInput) {
  const results = await ragSearch(query, k);
  return { results };
}
