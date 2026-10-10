from datetime import date

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DailyBiometrics, User

BASELINE_DAYS = 7
HISTORY_DAYS = 14


class DailyMetrics(BaseModel):
    date: date
    hrv_ms: float | None = None
    sleep_score: int | None = None
    resting_hr_bpm: int | None = None
    calories_kcal: int | None = None
    # Averages over the previous BASELINE_DAYS days, excluding this day. Computed in SQL.
    hrv_baseline_ms: float | None = None
    sleep_baseline: float | None = None
    resting_hr_baseline_bpm: float | None = None
    baseline_days: int = 0


class UserProfile(BaseModel):
    user_id: str
    name: str
    age: int | None = None
    weight_kg: float | None = None
    goal: str
    days: list[DailyMetrics]


def _rolling_avg(column):
    # ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING: the previous 7 days, not including today.
    return func.avg(column).over(order_by=DailyBiometrics.date, rows=(-BASELINE_DAYS, -1))


def get_user_days(db: Session, user_id: str) -> list[DailyMetrics]:
    stmt = (
        select(
            DailyBiometrics.date,
            DailyBiometrics.hrv_ms,
            DailyBiometrics.sleep_score,
            DailyBiometrics.resting_hr_bpm,
            DailyBiometrics.calories_kcal,
            _rolling_avg(DailyBiometrics.hrv_ms).label("hrv_baseline_ms"),
            _rolling_avg(DailyBiometrics.sleep_score).label("sleep_baseline"),
            _rolling_avg(DailyBiometrics.resting_hr_bpm).label("resting_hr_baseline_bpm"),
            func.count().over(order_by=DailyBiometrics.date, rows=(-BASELINE_DAYS, -1)).label("baseline_days"),
        )
        .where(DailyBiometrics.user_id == user_id)
        .order_by(DailyBiometrics.date)
    )
    rows = db.execute(stmt).mappings().all()
    return [DailyMetrics.model_validate(dict(row)) for row in rows[-HISTORY_DAYS:]]


def get_user(db: Session, user_id: str) -> UserProfile | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    return UserProfile(
        user_id=user.id,
        name=user.name,
        age=user.age,
        weight_kg=user.weight_kg,
        goal=user.goal,
        days=get_user_days(db, user_id),
    )


def upsert_user(
    db: Session, user_id: str, name: str, age: int | None, weight_kg: float | None, goal: str
) -> None:
    user = db.get(User, user_id) or User(id=user_id)
    user.name, user.age, user.weight_kg, user.goal = name, age, weight_kg, goal
    db.add(user)


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))
