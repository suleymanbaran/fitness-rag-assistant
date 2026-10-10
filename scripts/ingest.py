"""Embed data/protocols.json and load it into Qdrant.

Usage: python -m scripts.ingest [--query "..."] [--category recovery]
With QDRANT_URL set (the Docker Qdrant server) this can run while the API is up. Without it,
embedded Qdrant allows only one process to open the data folder, so stop the API first.
"""

import argparse

from openai import OpenAI

from app.config import get_settings
from app.rag.embeddings import Embedder
from app.rag.ingestion import ingest_protocols
from app.rag.vector_store import ProtocolStore, connect_qdrant


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="My HRV dropped and my legs feel heavy. Should I still squat?")
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    settings = get_settings()
    embedder = Embedder(OpenAI(api_key=settings.openai_api_key), settings.embedding_model)
    client = connect_qdrant(settings)
    store = ProtocolStore(client, settings.qdrant_collection)
    location = settings.qdrant_url or settings.qdrant_path

    try:
        count = ingest_protocols(embedder, store)
        print(f"Ingested {count} protocols into '{settings.qdrant_collection}' at {location}\n")

        hits = store.search(embedder.embed_one(args.query), top_k=settings.rag_top_k, category=args.category)
        print(f"Sample search: {args.query!r} (category={args.category})")
        for hit in hits:
            print(f"  {hit.score:.4f}  [{hit.category}] {hit.protocol_id}: {hit.title}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
