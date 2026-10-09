# Fitness RAG Assistant (MVP)

FastAPI backend that combines PostgreSQL biometrics, Qdrant RAG over recovery protocols, and OpenAI (GPT-4o) for personalized training guidance.

## Quick start

```bash
cp .env.example .env
# Set OPENAI_API_KEY in .env

docker compose up -d

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m scripts.seed_demo_data

uvicorn main:app --reload
```

OpenAPI docs: http://127.0.0.1:8000/docs

## Core endpoint

`POST /api/v1/analyze-my-day`

```json
{
  "user_id": "<uuid from seed script>",
  "query": "My HRV dropped 15% today, my CNS feels fried. How should I adjust my heavy leg day?"
}
```

On startup, the app creates SQL tables and seeds Qdrant with MVP recovery protocols when the collection is empty.
