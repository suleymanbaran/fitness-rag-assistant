from fastapi import FastAPI

from app.schemas import AskRequest, AskResponse

app = FastAPI(title="Fitness RAG Coach", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    # Placeholder until retrieval and generation exist (Steps 4-7).
    return AskResponse(
        answer=f"[stub] You asked: {payload.question}",
        sources=[],
    )
