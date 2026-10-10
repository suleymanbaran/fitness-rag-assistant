import os
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import RateLimiter, get_ask_limiter
from app.db.models import Base
from app.db.session import get_db
from app.main import app, get_embedder, get_generator, get_store
from app.rag.ingestion import ingest_protocols
from app.rag.vector_store import ProtocolStore
from scripts.seed import seed_demo_users
from tests.fakes import FakeEmbedder, FakeGenerator

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/fitness_coach_test"
)


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}):
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError:
        pytest.skip("Postgres is not reachable. Start it with: docker compose up -d")
    finally:
        admin.dispose()

    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    """A seeded session inside a transaction that is rolled back after the test.
    Commits made by the app become savepoints, so nothing leaks between tests."""
    with test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        seed_demo_users(session)
        app.dependency_overrides[get_db] = lambda: session
        try:
            yield session
        finally:
            app.dependency_overrides.pop(get_db, None)
            session.close()
            transaction.rollback()


@pytest.fixture
def fakes(db_session: Session) -> Iterator[SimpleNamespace]:
    embedder = FakeEmbedder()
    generator = FakeGenerator()
    store = ProtocolStore(QdrantClient(":memory:"), "protocols")
    ingest_protocols(embedder, store)

    limiter = RateLimiter()
    overrides = {
        get_embedder: lambda: embedder,
        get_generator: lambda: generator,
        get_store: lambda: store,
        get_ask_limiter: lambda: limiter,
    }
    app.dependency_overrides.update(overrides)
    # No `with TestClient(...)`: the lifespan (real OpenAI and on-disk Qdrant) is skipped.
    yield SimpleNamespace(client=TestClient(app), generator=generator, store=store, db=db_session)
    for dependency in overrides:
        app.dependency_overrides.pop(dependency, None)
