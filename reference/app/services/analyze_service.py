from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.analyze import AnalyzeMyDayRequest, AnalyzeMyDayResponse
from app.schemas.biometrics import DailyBiometricsRead
from app.services.biometrics_service import get_recent_biometrics
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService


class AnalyzeService:
    def __init__(self, rag: RAGService, llm: LLMService) -> None:
        self.rag = rag
        self.llm = llm

    def analyze_my_day(self, db: Session, payload: AnalyzeMyDayRequest) -> AnalyzeMyDayResponse:
        user = db.get(User, payload.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {payload.user_id} not found",
            )

        biometrics = get_recent_biometrics(db, payload.user_id)
        protocols = self.rag.retrieve_protocols(payload.query, biometrics)
        recommendation = self.llm.generate_recommendation(
            user_query=payload.query,
            biometrics=biometrics,
            protocols=protocols,
        )

        return AnalyzeMyDayResponse(
            user_id=payload.user_id,
            query=payload.query,
            recent_biometrics=[DailyBiometricsRead.model_validate(b) for b in biometrics],
            retrieved_protocols=protocols,
            recommendation=recommendation,
        )
