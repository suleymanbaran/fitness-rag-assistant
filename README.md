# Fitness RAG Coach

A RAG-based AI fitness coach, built phase by phase as a learning project.
`reference/` holds an earlier generated scaffold kept for comparison only.

## Run

```bash
cp .env.example .env   # set OPENAI_API_KEY
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Docs: http://127.0.0.1:8000/docs
