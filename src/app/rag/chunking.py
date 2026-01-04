from __future__ import annotations

from typing import Iterable, List


def chunk_markdown(text: str, size: int = 800, overlap: int = 120) -> List[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    chunks: List[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(length, start + size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap if end < length else end
        if start < 0:
            start = 0
    return chunks


def window(iterable: Iterable[str], size: int) -> Iterable[str]:
    buffer: List[str] = []
    for item in iterable:
        buffer.append(item)
        if len(buffer) == size:
            yield "\n".join(buffer)
            buffer = []
    if buffer:
        yield "\n".join(buffer)
