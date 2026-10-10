from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import DailyBiometrics

METRIC_FIELDS = ("hrv_ms", "sleep_score", "sleep_minutes", "resting_hr_bpm", "calories_kcal")


def upsert_daily_metrics(db: Session, user_id: str, day: date, source: str, **metrics: Any) -> None:
    """Insert or update one user-day. Only the metrics passed in are overwritten, so a Google sync
    (HRV, sleep) and a FatSecret sync (calories) can fill the same row without erasing each other."""
    values = {k: v for k, v in metrics.items() if k in METRIC_FIELDS and v is not None}
    stmt = insert(DailyBiometrics).values(user_id=user_id, date=day, source=source, **values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_biometrics_user_date",
        set_={**values, "source": source, "updated_at": func.now()},
    )
    db.execute(stmt)
