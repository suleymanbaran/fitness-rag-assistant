from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.biometrics import DailyBiometricsRead


class AnalyzeMyDayRequest(BaseModel):
    user_id: UUID
    query: str = Field(..., min_length=3, max_length=4000)


class RetrievedProtocol(BaseModel):
    title: str
    category: str
    content: str
    relevance_score: float | None = None


class AnalyzeMyDayResponse(BaseModel):
    user_id: UUID
    query: str
    recent_biometrics: list[DailyBiometricsRead]
    retrieved_protocols: list[RetrievedProtocol]
    recommendation: str
