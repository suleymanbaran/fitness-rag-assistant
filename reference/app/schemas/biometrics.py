from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DailyBiometricsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    recorded_on: date
    hrv_ms: float | None = None
    sleep_score: int | None = Field(default=None, ge=0, le=100)
    resting_heart_rate_bpm: int | None = Field(default=None, ge=30, le=220)
    weight_kg: float | None = Field(default=None, gt=0)
    calorie_intake_kcal: int | None = Field(default=None, ge=0)
    created_at: datetime
