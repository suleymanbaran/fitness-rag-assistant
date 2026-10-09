# Fitness RAG Coach

A RAG-based AI fitness coach, built phase by phase as a learning project.
`reference/` holds an earlier generated scaffold kept for comparison only.

## Phase 1: the core RAG loop

```text
question ─► embed ─► Qdrant top-k protocols ─┐
user_id ──► exact lookup in users.json ──────┼─► prompt ─► gpt-4o-mini ─► answer + sources
```

| Path | Role |
|---|---|
| `data/protocols.json` | Unstructured knowledge, searched by meaning (vector DB) |
| `data/users.json` | Structured user metrics, looked up exactly by `user_id` |
| `app/rag/embeddings.py` | Text to vectors (OpenAI embeddings) |
| `app/rag/vector_store.py` | Qdrant collection: recreate, upsert, filtered search |
| `app/rag/prompt.py` | System rules, computed baselines, retrieved protocols |
| `app/rag/generator.py` | Chat completion call |
| `app/main.py` | FastAPI app, lifespan, dependencies, `POST /ask` |
| `scripts/cosine_playground.py` | Brute-force cosine search in NumPy |
| `scripts/ingest.py` | Embed protocols and load them into Qdrant |

## Run

```bash
cp .env.example .env   # set OPENAI_API_KEY
source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.cosine_playground "my nervous system feels fried before leg day"
python -m scripts.ingest            # run while the server is stopped
uvicorn app.main:app --reload
```

Docs: http://127.0.0.1:8000/docs

```bash
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"user_id": "u1", "question": "My HRV dropped and my CNS feels fried. How should I adjust leg day?"}'
```

Embedded Qdrant lets only one process open `qdrant_data/` at a time, so stop the server before re-ingesting.

## Test

```bash
python -m pytest -q
```

Tests use an in-memory Qdrant and fake embedder/generator, so they need no API key.
