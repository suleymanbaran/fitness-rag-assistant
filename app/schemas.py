from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    user_id: str = Field(..., examples=["u1"])
    question: str = Field(..., min_length=3, max_length=2000)


class Source(BaseModel):
    protocol_id: str
    title: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
