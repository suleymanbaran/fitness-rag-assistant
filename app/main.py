import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response
from openai import APIError, OpenAI
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.auth import RateLimiter, authorize, current_user_id, get_ask_limiter
from app.config import Settings, get_settings
from app.data_access.biometrics import upsert_daily_metrics
from app.data_access.users import DailyMetrics, UserProfile, get_user, get_user_days, list_users, upsert_user
from app.db.models import User
from app.db.session import get_db
from app.rag.demo import HashingEmbedder, PromptEchoGenerator
from app.rag.embeddings import Embedder
from app.rag.generator import Generator
from app.rag.ingestion import ingest_protocols
from app.rag.prompt import build_messages
from app.rag.vector_store import ProtocolStore, connect_qdrant
from app.schemas import (
    USER_ID_PATTERN,
    AskRequest,
    AskResponse,
    DayMetricsIn,
    ProfileIn,
    Source,
    UserSummary,
)

logger = logging.getLogger("fitness_coach")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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
        openai_client = OpenAI(
            api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds, max_retries=2
        )
        qdrant_client = connect_qdrant(settings)
        app.state.embedder = Embedder(openai_client, settings.embedding_model)
        app.state.generator = Generator(openai_client, settings.chat_model)
        app.state.store = ProtocolStore(qdrant_client, settings.qdrant_collection)

    yield
    qdrant_client.close()


app = FastAPI(title="Fitness RAG Coach", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    # Logs method, path, status and timing only: bodies hold health metrics and stay out of logs.
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request_id=%s %s %s status=%d %.0fms",
        request_id, request.method, request.url.path, response.status_code, elapsed_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


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
def users(db: Session = Depends(get_db), current: str | None = Depends(current_user_id)) -> list[UserSummary]:
    return [
        UserSummary(user_id=u.id, name=u.name, goal=u.goal)
        for u in list_users(db)
        if current is None or u.id == current
    ]


@app.get("/users/{user_id}", response_model=UserProfile)
def user_detail(
    user_id: str, db: Session = Depends(get_db), current: str | None = Depends(current_user_id)
) -> UserProfile:
    authorize(user_id, current)
    user = get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


@app.put("/users/{user_id}", response_model=UserProfile)
def save_profile(
    profile: ProfileIn,
    user_id: str = Path(..., pattern=USER_ID_PATTERN),
    db: Session = Depends(get_db),
    current: str | None = Depends(current_user_id),
) -> UserProfile:
    authorize(user_id, current)
    upsert_user(db, user_id, **profile.model_dump())
    db.commit()
    return get_user(db, user_id)


@app.put("/users/{user_id}/days/{day}", response_model=DailyMetrics)
def log_day(
    day: date,
    metrics: DayMetricsIn,
    user_id: str = Path(..., pattern=USER_ID_PATTERN),
    db: Session = Depends(get_db),
    current: str | None = Depends(current_user_id),
) -> DailyMetrics:
    authorize(user_id, current)
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    if day > date.today():
        raise HTTPException(status_code=422, detail="Cannot log metrics for a future date")
    upsert_daily_metrics(db, user_id, day, source="manual", **metrics.model_dump(exclude_none=True))
    db.commit()
    return next(d for d in get_user_days(db, user_id) if d.date == day)


@app.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current: str | None = Depends(current_user_id),
    limiter: RateLimiter = Depends(get_ask_limiter),
    embedder: Embedder = Depends(get_embedder),
    store: ProtocolStore = Depends(get_store),
    generator: Generator = Depends(get_generator),
) -> AskResponse:
    authorize(payload.user_id, current)
    limiter.check(payload.user_id, settings.ask_rate_limit_per_minute)
    user = get_user(db, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {payload.user_id} not found")
    if not store.is_ready():
        raise HTTPException(status_code=503, detail="Knowledge base is empty. Run: python -m scripts.ingest")

    try:
        query_vector = embedder.embed_one(payload.question)
        chunks = store.search(query_vector, top_k=settings.rag_top_k, category=payload.category)
        answer = generator.generate(build_messages(payload.question, user, chunks))
    except APIError as exc:
        logger.warning("OpenAI call failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The AI service failed. Try again in a moment.") from exc

    return AskResponse(
        answer=answer,
        sources=[
            Source(protocol_id=c.protocol_id, title=c.title, category=c.category, score=round(c.score, 4))
            for c in chunks
        ],
    )
