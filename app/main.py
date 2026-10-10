from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from openai import OpenAI
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.data_access.users import UserProfile, get_user, list_users
from app.db.session import get_db
from app.rag.demo import HashingEmbedder, PromptEchoGenerator
from app.rag.embeddings import Embedder
from app.rag.generator import Generator
from app.rag.ingestion import ingest_protocols
from app.rag.prompt import build_messages
from app.rag.vector_store import ProtocolStore, connect_qdrant
from app.schemas import AskRequest, AskResponse, Source, UserSummary


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    if settings.demo_mode:
        qdrant_client = QdrantClient(":memory:")
        app.state.embedder = HashingEmbedder()
        app.state.generator = PromptEchoGenerator()
        app.state.store = ProtocolStore(qdrant_client, settings.qdrant_collection)
        ingest_protocols(app.state.embedder, app.state.store)
    else:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to .env, or set DEMO_MODE=true to run offline."
            )
        openai_client = OpenAI(api_key=settings.openai_api_key)
        qdrant_client = connect_qdrant(settings)
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


@app.get("/users", response_model=list[UserSummary])
def users(db: Session = Depends(get_db)) -> list[UserSummary]:
    return [UserSummary(user_id=u.id, name=u.name, goal=u.goal) for u in list_users(db)]


@app.get("/users/{user_id}", response_model=UserProfile)
def user_detail(user_id: str, db: Session = Depends(get_db)) -> UserProfile:
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


@app.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    embedder: Embedder = Depends(get_embedder),
    store: ProtocolStore = Depends(get_store),
    generator: Generator = Depends(get_generator),
) -> AskResponse:
    user = get_user(db, payload.user_id)
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
