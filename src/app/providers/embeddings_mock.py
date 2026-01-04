import hashlib
from typing import List


def embed(texts: List[str], dim: int = 384) -> List[List[float]]:
    vectors: List[List[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(dim)]
        vectors.append(vector)
    return vectors
