"""Offline stand-ins for OpenAI, used when DEMO_MODE=true and in tests."""

import hashlib
import re

import numpy as np

HASH_DIM = 256


class HashingEmbedder:
    """Bag-of-words hashing: texts that share words get similar vectors. Crude, but free and offline."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        vector = np.zeros(HASH_DIM)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % HASH_DIM
            vector[bucket] += 1.0
        norm = np.linalg.norm(vector)
        return (vector / norm if norm else vector).tolist()


class PromptEchoGenerator:
    """Instead of calling GPT, returns the exact prompt GPT would have received."""

    def generate(self, messages: list[dict]) -> str:
        user_message = messages[-1]["content"]
        return (
            "**Demo mode:** no OpenAI key is configured, so this is not a real AI answer. "
            "Below is exactly what would be sent to GPT: the user's computed metrics, "
            "the retrieved protocols, and the question.\n\n"
            f"```text\n{user_message}\n```"
        )
