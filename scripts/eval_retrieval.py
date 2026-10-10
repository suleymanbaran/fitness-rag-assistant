"""Score retrieval against data/eval_questions.json.

Usage: python -m scripts.eval_retrieval [--k 1 3 5] [--demo]
Protocols are embedded into a fresh in-memory Qdrant, so this measures the current
protocols.json and embedding model without touching the API's collection.
--demo uses the offline word-hashing embedder instead of OpenAI (no key needed, much weaker).
"""

import argparse

from openai import OpenAI
from qdrant_client import QdrantClient

from app.config import get_settings
from app.rag.demo import HashingEmbedder
from app.rag.embeddings import Embedder
from app.rag.evaluation import evaluate_retrieval, load_eval_cases
from app.rag.ingestion import ingest_protocols
from app.rag.vector_store import ProtocolStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--demo", action="store_true", help="Use the offline hashing embedder")
    args = parser.parse_args()

    settings = get_settings()
    if args.demo:
        embedder, model = HashingEmbedder(), "hashing (demo)"
    else:
        embedder, model = Embedder(OpenAI(api_key=settings.openai_api_key), settings.embedding_model), settings.embedding_model

    store = ProtocolStore(QdrantClient(":memory:"), "eval")
    ingest_protocols(embedder, store)
    cases = load_eval_cases()
    report = evaluate_retrieval(embedder, store, cases, k=max(args.k))

    print(f"Embedding model: {model}. {len(cases)} questions.\n")
    print(f"{'k':>3}  {'hit rate':>8}  {'recall':>6}  {'MRR':>5}")
    for k in sorted(args.k):
        r = report.at(k)
        print(f"{k:>3}  {r.hit_rate:>8.2f}  {r.recall:>6.2f}  {r.mrr:>5.2f}")

    serving_k = report.at(min(settings.rag_top_k, report.k))
    misses = [r for r in serving_k.results if not r.hit]
    print(f"\nMisses at k={serving_k.k} (RAG_TOP_K): {len(misses)}")
    for r in misses:
        print(f"  {r.case.question}\n    expected {r.case.relevant}, got {r.retrieved}")


if __name__ == "__main__":
    main()
