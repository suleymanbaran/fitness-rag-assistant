from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.data_access.protocols import Category

Goal = Literal["strength", "muscle_gain", "fat_loss", "endurance", "general_fitness"]
USER_ID_PATTERN = r"^[a-z0-9_-]{1,64}$"


class AskRequest(BaseModel):
    user_id: str = Field(..., examples=["u1"])
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        examples=["My HRV dropped and my CNS feels fried. How should I adjust today's heavy leg day?"],
    )
    category: Category | None = Field(None, description="Restrict retrieval to one protocol category")


class UserSummary(BaseModel):
    user_id: str
    name: str
    goal: str


class ProfileIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["Suleyman"])
    age: int | None = Field(None, ge=10, le=110)
    weight_kg: float | None = Field(None, gt=20, lt=400)
    goal: Goal = "general_fitness"


class DayMetricsIn(BaseModel):
    """Only the metrics you send are written; omitted ones keep their stored value."""

    hrv_ms: float | None = Field(None, gt=0, lt=400)
    sleep_score: int | None = Field(None, ge=0, le=100)
    sleep_minutes: int | None = Field(None, ge=0, le=1440)
    resting_hr_bpm: int | None = Field(None, ge=20, le=250)
    calories_kcal: int | None = Field(None, ge=0, le=20000)

    @model_validator(mode="after")
    def at_least_one_metric(self) -> "DayMetricsIn":
        if all(v is None for v in self.model_dump().values()):
            raise ValueError("Send at least one metric")
        return self


class IntegrationStatus(BaseModel):
    provider: str
    configured: bool
    connected: bool
    last_synced_at: datetime | None = None
    last_error: str | None = None


class ConnectResponse(BaseModel):
    authorization_url: str


class SyncResultOut(BaseModel):
    provider: str
    days_updated: int
    error: str | None = None
    reconnect: bool = False


class Source(BaseModel):
    protocol_id: str
    title: str
    category: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
