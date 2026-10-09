import hashlib
import re

import numpy as np

FAKE_DIM = 256


class FakeEmbedder:
    """Bag-of-words hashing embedder: deterministic, offline, and word overlap means similarity."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        vector = np.zeros(FAKE_DIM)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % FAKE_DIM
            vector[bucket] += 1.0
        norm = np.linalg.norm(vector)
        return (vector / norm if norm else vector).tolist()


class FakeGenerator:
    def __init__(self) -> None:
        self.last_messages: list[dict] | None = None

    def generate(self, messages: list[dict]) -> str:
        self.last_messages = messages
        return "Fake answer [rec-hrv-autoregulation]"
