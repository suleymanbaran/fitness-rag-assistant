from app.data_access.protocols import load_protocols
from app.rag.embeddings import Embedder
from app.rag.vector_store import ProtocolStore


def ingest_protocols(embedder: Embedder, store: ProtocolStore) -> int:
    protocols = load_protocols()
    vectors = embedder.embed([f"{p.title}\n{p.text}" for p in protocols])
    store.recreate(vector_size=len(vectors[0]))
    store.upsert(protocols, vectors)
    return store.count()
