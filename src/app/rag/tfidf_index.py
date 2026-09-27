from __future__ import annotations

import threading
from typing import Dict, List, Optional, Set, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TFIDFIndex:
    def __init__(self, *, persistent=False) -> None:
        self.persistent = persistent
        self._lock = threading.Lock()
        self._search_slot = threading.Lock()
        self.vectorizer = TfidfVectorizer()
        self.documents: List[Tuple[str, str, str]] = []  # (note_id, chunk_id, text)
        self.matrix = None
        self._loaded = False
        self._dirty = True

    def upsert(self, note_id: str, chunks: List[Tuple[str, str]]) -> None:
        with self._lock:
            self.documents = [doc for doc in self.documents if doc[0] != note_id]
            for chunk_id, text in chunks:
                self.documents.append((note_id, chunk_id, text))
            self._dirty = True

    def remove(self, note_id: str) -> None:
        with self._lock:
            self.documents = [doc for doc in self.documents if doc[0] != note_id]
            self._dirty = True

    def search(self, query: str, limit: int = 8, *, allowed_note_ids: Optional[Set[str]] = None) -> List[Dict[str, object]]:
        from fastapi import HTTPException
        if not self._search_slot.acquire(blocking=False):
            raise HTTPException(503, 'Search index busy; retry later', headers={'Retry-After':'1'})
        try:
            return self._search(query, limit, allowed_note_ids=allowed_note_ids)
        finally:
            self._search_slot.release()

    def _search(self, query, limit, *, allowed_note_ids):
        self._ensure_loaded()
        with self._lock:
            if not self.documents:
                return []
            documents = list(self.documents)
            dirty = self._dirty
            vectorizer, matrix = self.vectorizer, self.matrix
        # The expensive fit never holds the mutation lock or a database session.
        if dirty:
            vectorizer = TfidfVectorizer()
            try:
                matrix = vectorizer.fit_transform([text for _, _, text in documents])
            except ValueError as exc:
                if 'empty vocabulary' not in str(exc):
                    raise
                matrix = None
            with self._lock:
                if self.documents == documents:
                    self.vectorizer, self.matrix, self._dirty = vectorizer, matrix, False
        if matrix is None:
            return []
        query_vec = vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, matrix).flatten()
        scored = [(doc, score) for doc, score in zip(documents, similarities)
                  if allowed_note_ids is None or doc[0] in allowed_note_ids]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [{'note_id':n, 'chunk_id':c, 'text':t, 'score':float(score)}
                for (n,c,t), score in scored[:limit]]

    def _ensure_loaded(self):
        if not self.persistent:
            return
        with self._lock:
            if self._loaded:
                return
            before = list(self.documents)
        from app.db.models import NoteChunk, Note
        from app.db.session import get_session
        with get_session() as session:
            rows = session.query(NoteChunk.note_id, NoteChunk.id, NoteChunk.text).join(
                Note, Note.id == NoteChunk.note_id).filter(Note.tombstone.is_(False)).all()
        with self._lock:
            if self.documents == before:
                self.documents = [tuple(row) for row in rows]
                self._loaded = True
                self._dirty = True

    def _rebuild(self) -> None:
        if not self.documents:
            self.matrix = None
            return
        corpus = [text for (_, _, text) in self.documents]
        try:
            self.matrix = self.vectorizer.fit_transform(corpus)
        except ValueError as exc:
            if "empty vocabulary" not in str(exc):
                raise
            self.matrix = None


index = TFIDFIndex(persistent=True)
