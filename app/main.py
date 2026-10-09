from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from openai import OpenAI
from qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.data_access.users import get_user
from app.rag.embeddings import Embedder
from app.rag.generator import Generator
from app.rag.prompt import build_messages
from app.rag.vector_store import ProtocolStore
from app.schemas import AskRequest, AskResponse, Source


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")

    openai_client = OpenAI(api_key=settings.openai_api_key)
    qdrant_client = QdrantClient(path=settings.qdrant_path)
    app.state.embedder = Embedder(openai_client, settings.embedding_model)
    app.state.generator = Generator(openai_client, settings.chat_model)
    app.state.store = ProtocolStore(qdrant_client, settings.qdrant_collection)
    yield
    qdrant_client.close()


app = FastAPI(title="Fitness RAG Coach", version="0.1.0", lifespan=lifespan)


def get_embedder(request: Request) -> Embedder:
    return request.app.state.embedder


def get_generator(request: Request) -> Generator:
    return request.app.state.generator


def get_store(request: Request) -> ProtocolStore:
    return request.app.state.store


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    settings: Settings = Depends(get_settings),
    embedder: Embedder = Depends(get_embedder),
    store: ProtocolStore = Depends(get_store),
    generator: Generator = Depends(get_generator),
) -> AskResponse:
    user = get_user(payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {payload.user_id} not found")
    if not store.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Knowledge base is empty. Stop the server and run: python -m scripts.ingest",
        )

    query_vector = embedder.embed_one(payload.question)
    chunks = store.search(query_vector, top_k=settings.rag_top_k, category=payload.category)
    answer = generator.generate(build_messages(payload.question, user, chunks))

    return AskResponse(
        answer=answer,
        sources=[
            Source(protocol_id=c.protocol_id, title=c.title, category=c.category, score=round(c.score, 4))
            for c in chunks
        ],
    )
