from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import get_settings
from app.main import app, get_embedder, get_generator, get_store
from app.rag.demo import PromptEchoGenerator
from app.rag.generator import Generator
from app.rag.ingestion import ingest_protocols
from app.rag.vector_store import ProtocolStore
from tests.fakes import FakeEmbedder, FakeGenerator


@pytest.fixture
def fakes():
    embedder = FakeEmbedder()
    generator = FakeGenerator()
    store = ProtocolStore(QdrantClient(":memory:"), "protocols")
    ingest_protocols(embedder, store)

    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_generator] = lambda: generator
    app.dependency_overrides[get_store] = lambda: store
    # No `with TestClient(...)`: the lifespan (real OpenAI and on-disk Qdrant) is skipped.
    yield SimpleNamespace(client=TestClient(app), generator=generator, store=store)
    app.dependency_overrides.clear()


def test_health(fakes):
    assert fakes.client.get("/health").json() == {"status": "ok"}


def test_ask_returns_answer_and_ranked_sources(fakes):
    r = fakes.client.post("/ask", json={"user_id": "u1", "question": "My HRV dropped, should I train legs?"})

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Fake answer [rec-hrv-autoregulation]"
    assert len(body["sources"]) == 3
    scores = [s["score"] for s in body["sources"]]
    assert scores == sorted(scores, reverse=True)
    assert body["sources"][0]["protocol_id"] == "rec-hrv-autoregulation"


def test_prompt_contains_user_metrics_and_retrieved_protocols(fakes):
    fakes.client.post("/ask", json={"user_id": "u1", "question": "My HRV dropped, should I train legs?"})

    system, user = fakes.generator.last_messages
    assert system["role"] == "system"
    assert "HRV 55.0 ms vs 66.5 ms (-17.3%)" in user["content"]
    assert "[rec-hrv-autoregulation]" in user["content"]
    assert user["content"].endswith("Question: My HRV dropped, should I train legs?")


def test_category_filter_restricts_sources(fakes):
    r = fakes.client.post(
        "/ask", json={"user_id": "u2", "question": "How much protein do I need?", "category": "nutrition"}
    )

    assert r.status_code == 200
    assert {s["category"] for s in r.json()["sources"]} == {"nutrition"}


def test_unknown_user_returns_404(fakes):
    r = fakes.client.post("/ask", json={"user_id": "nobody", "question": "Hello coach"})
    assert r.status_code == 404


def test_invalid_input_returns_422(fakes):
    assert fakes.client.post("/ask", json={"user_id": "u1", "question": "hi"}).status_code == 422
    assert (
        fakes.client.post("/ask", json={"user_id": "u1", "question": "Hello", "category": "magic"}).status_code
        == 422
    )


def test_empty_knowledge_base_returns_503(fakes):
    app.dependency_overrides[get_store] = lambda: ProtocolStore(QdrantClient(":memory:"), "protocols")
    r = fakes.client.post("/ask", json={"user_id": "u1", "question": "Hello coach"})
    assert r.status_code == 503


def test_users_list_and_detail(fakes):
    users = fakes.client.get("/users").json()
    assert {u["user_id"] for u in users} == {"u1", "u2"}
    assert set(users[0]) == {"user_id", "name", "goal"}

    detail = fakes.client.get("/users/u1").json()
    assert detail["name"] == "Ali"
    assert len(detail["days"]) == 7
    assert fakes.client.get("/users/nobody").status_code == 404


def test_demo_mode_runs_full_app_without_openai(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:  # `with` runs the lifespan, so startup is tested too
            r = client.post("/ask", json={"user_id": "u1", "question": "My HRV dropped, should I squat?"})
    finally:
        get_settings.cache_clear()

    assert r.status_code == 200
    assert r.json()["answer"].startswith("**Demo mode:**")
    assert "HRV 55.0 ms vs 66.5 ms" in r.json()["answer"]
    assert len(r.json()["sources"]) == 3


def test_prompt_echo_generator_shows_last_message():
    answer = PromptEchoGenerator().generate([{"role": "system", "content": "rules"}, {"role": "user", "content": "data"}])
    assert "```text\ndata\n```" in answer
    assert "rules" not in answer


def test_generator_reads_message_content_from_openai_response():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Rest today."))])
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return response

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    generator = Generator(client, model="gpt-4o-mini")

    assert generator.generate([{"role": "user", "content": "hi"}]) == "Rest today."
    assert calls["model"] == "gpt-4o-mini"
    assert calls["temperature"] == 0.2
