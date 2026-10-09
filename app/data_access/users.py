import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

USERS_PATH = Path(__file__).resolve().parents[2] / "data" / "users.json"


class DailyMetrics(BaseModel):
    date: date
    hrv_ms: float | None = None
    sleep_score: int | None = None
    resting_hr_bpm: int | None = None
    calories_kcal: int | None = None


class UserProfile(BaseModel):
    user_id: str
    name: str
    age: int
    weight_kg: float
    goal: str
    days: list[DailyMetrics]


@lru_cache
def _load_users() -> dict[str, UserProfile]:
    raw = json.loads(USERS_PATH.read_text())
    users = [UserProfile.model_validate(item) for item in raw]
    return {user.user_id: user for user in users}


def get_user(user_id: str) -> UserProfile | None:
    return _load_users().get(user_id)
