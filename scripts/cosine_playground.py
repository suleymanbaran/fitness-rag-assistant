"""Brute-force semantic search with NumPy, before using a vector database.

Usage: python -m scripts.cosine_playground "my nervous system feels fried before leg day"
"""

import argparse

import numpy as np
from openai import OpenAI

from app.config import get_settings
from app.data_access.protocols import load_protocols
from app.rag.embeddings import Embedder


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    settings = get_settings()
    embedder = Embedder(OpenAI(api_key=settings.openai_api_key), settings.embedding_model)
    protocols = load_protocols()

    doc_vectors = np.array(embedder.embed([p.text for p in protocols]))
    query_vector = np.array(embedder.embed_one(args.query))

    print(f"Document matrix shape: {doc_vectors.shape} (documents x dimensions)")
    print(f"Query vector length (L2 norm): {np.linalg.norm(query_vector):.4f}\n")

    scores = [cosine_similarity(query_vector, doc) for doc in doc_vectors]
    ranked = sorted(zip(scores, protocols), key=lambda pair: pair[0], reverse=True)

    print(f"Query: {args.query!r}\n")
    for rank, (score, protocol) in enumerate(ranked, start=1):
        marker = "  <- top-k" if rank <= args.top_k else ""
        print(f"{rank:>2}. {score:.4f}  [{protocol.category}] {protocol.title}{marker}")

    # OpenAI embeddings are normalized to length 1, so a plain dot product gives the same ranking.
    dot_scores = doc_vectors @ query_vector
    print(f"\nMax |cosine - dot| difference: {np.max(np.abs(np.array(scores) - dot_scores)):.2e}")


if __name__ == "__main__":
    main()
