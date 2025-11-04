from __future__ import annotations

import math
from typing import Dict, List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TFIDFIndex:
    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer()
        self.documents: List[Tuple[str, str, str]] = []  # (note_id, chunk_id, text)
        self.matrix = None

    def upsert(self, note_id: str, chunks: List[Tuple[str, str]]) -> None:
        # chunks: list of (chunk_id, text)
        self.documents = [doc for doc in self.documents if doc[0] != note_id]
        for chunk_id, text in chunks:
            self.documents.append((note_id, chunk_id, text))
        self._rebuild()

    def remove(self, note_id: str) -> None:
        self.documents = [doc for doc in self.documents if doc[0] != note_id]
        self._rebuild()

    def search(self, query: str, limit: int = 8) -> List[Dict[str, object]]:
        if not self.documents:
            return []
        query_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self.matrix).flatten()
        scored = list(zip(self.documents, similarities))
        scored.sort(key=lambda item: item[1], reverse=True)
        results = []
        for (note_id, chunk_id, text), score in scored[:limit]:
            results.append({
                "note_id": note_id,
                "chunk_id": chunk_id,
                "text": text,
                "score": float(score),
            })
        return results

    def _rebuild(self) -> None:
        if not self.documents:
            self.matrix = None
            return
        corpus = [text for (_, _, text) in self.documents]
        self.matrix = self.vectorizer.fit_transform(corpus)


index = TFIDFIndex()
