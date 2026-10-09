from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.database import Base, engine
from app.routers.analyze import router as analyze_router
from app.services.rag_service import RAGService


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    rag = RAGService.from_settings()
    try:
        rag.seed_if_empty()
    except Exception as exc:  # noqa: BLE001 — MVP: allow API boot if Qdrant is down
        print(f"Warning: RAG seed skipped ({exc})")
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Fitness RAG Assistant",
        version="0.1.0",
        description="B2C RAG-powered personal fitness and recovery coach",
        lifespan=lifespan,
    )
    application.include_router(analyze_router)
    return application


app = create_app()
