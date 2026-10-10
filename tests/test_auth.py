from datetime import date

import pytest

from app.auth import hash_token
from app.config import Settings, get_settings
from app.db.models import User
from app.main import app

ALI_TOKEN = "ali-secret-token"


@pytest.fixture
def secured(fakes):
    """The app with AUTH_ENABLED=true; Ali has a token, Elif has none."""
    fakes.db.get(User, "u1").api_token_hash = hash_token(ALI_TOKEN)
    fakes.db.commit()
    app.dependency_overrides[get_settings] = lambda: Settings(auth_enabled=True, ask_rate_limit_per_minute=2)
    yield fakes
    app.dependency_overrides.pop(get_settings, None)


def auth(token: str = ALI_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_missing_or_wrong_token_is_401(secured):
    r = secured.client.get("/users")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert secured.client.get("/users", headers=auth("wrong")).status_code == 401
    assert secured.client.get("/health").status_code == 200


def test_user_sees_and_changes_only_own_data(secured):
    assert secured.client.get("/users", headers=auth()).json() == [
        {"user_id": "u1", "name": "Ali", "goal": "strength"}
    ]
    assert secured.client.get("/users/u1", headers=auth()).status_code == 200

    today = date.today()
    forbidden = [
        secured.client.get("/users/u2", headers=auth()),
        secured.client.put("/users/u2", headers=auth(), json={"name": "Hacked"}),
        secured.client.put(f"/users/u2/days/{today}", headers=auth(), json={"hrv_ms": 1}),
        secured.client.put("/users/newbie", headers=auth(), json={"name": "Squatter"}),
        secured.client.post("/ask", headers=auth(), json={"user_id": "u2", "question": "What is Elif's HRV?"}),
    ]
    assert [r.status_code for r in forbidden] == [403] * 5
    assert secured.db.get(User, "u2").name == "Elif"
    assert secured.db.get(User, "newbie") is None


def test_ask_is_rate_limited_per_user(secured):
    question = {"user_id": "u1", "question": "Should I train today?"}
    codes = [secured.client.post("/ask", headers=auth(), json=question).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = secured.client.post("/ask", headers=auth(), json=question)
    assert int(r.headers["Retry-After"]) > 0


def test_requests_get_an_id_header(fakes):
    assert fakes.client.get("/health", headers={"X-Request-ID": "abc123"}).headers["X-Request-ID"] == "abc123"
    assert len(fakes.client.get("/health").headers["X-Request-ID"]) == 12
