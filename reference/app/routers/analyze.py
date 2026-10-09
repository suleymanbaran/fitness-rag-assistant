from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analyze import AnalyzeMyDayRequest, AnalyzeMyDayResponse
from app.services.analyze_service import AnalyzeService
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1", tags=["analyze"])


def get_analyze_service() -> AnalyzeService:
    return AnalyzeService(rag=RAGService.from_settings(), llm=LLMService.from_settings())


@router.post("/analyze-my-day", response_model=AnalyzeMyDayResponse)
def analyze_my_day(
    payload: AnalyzeMyDayRequest,
    db: Session = Depends(get_db),
    service: AnalyzeService = Depends(get_analyze_service),
) -> AnalyzeMyDayResponse:
    return service.analyze_my_day(db, payload)
