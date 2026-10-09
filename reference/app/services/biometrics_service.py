from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.daily_biometrics import DailyBiometrics


def get_recent_biometrics(db: Session, user_id: UUID, limit: int = 14) -> list[DailyBiometrics]:
    stmt = (
        select(DailyBiometrics)
        .where(DailyBiometrics.user_id == user_id)
        .order_by(DailyBiometrics.recorded_on.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
