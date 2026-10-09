"""Embed data/protocols.json and load it into the embedded Qdrant database.

Usage: python -m scripts.ingest [--query "..."] [--category recovery]
Stop the API server first: embedded Qdrant allows only one process to open the data folder.
"""

import argparse

from openai import OpenAI
from qdrant_client import QdrantClient

from app.config import get_settings
from app.data_access.protocols import load_protocols
from app.rag.embeddings import Embedder
from app.rag.vector_store import ProtocolStore


def ingest(embedder: Embedder, store: ProtocolStore) -> int:
    protocols = load_protocols()
    vectors = embedder.embed([f"{p.title}\n{p.text}" for p in protocols])
    store.recreate(vector_size=len(vectors[0]))
    store.upsert(protocols, vectors)
    return store.count()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="My HRV dropped and my legs feel heavy. Should I still squat?")
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    settings = get_settings()
    embedder = Embedder(OpenAI(api_key=settings.openai_api_key), settings.embedding_model)
    client = QdrantClient(path=settings.qdrant_path)
    store = ProtocolStore(client, settings.qdrant_collection)

    try:
        count = ingest(embedder, store)
        print(f"Ingested {count} protocols into '{settings.qdrant_collection}' at {settings.qdrant_path}\n")

        hits = store.search(embedder.embed_one(args.query), top_k=settings.rag_top_k, category=args.category)
        print(f"Sample search: {args.query!r} (category={args.category})")
        for hit in hits:
            print(f"  {hit.score:.4f}  [{hit.category}] {hit.protocol_id}: {hit.title}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
