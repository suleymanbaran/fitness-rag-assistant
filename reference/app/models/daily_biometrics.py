from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyBiometrics(Base):
    __tablename__ = "daily_biometrics"
    __table_args__ = (UniqueConstraint("user_id", "recorded_on", name="uq_user_biometrics_date"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Heart rate variability in ms")
    sleep_score: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="0-100 sleep quality score")
    resting_heart_rate_bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    calorie_intake_kcal: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="daily_biometrics")


from app.models.user import User  # noqa: E402
