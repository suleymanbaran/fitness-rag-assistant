from pydantic import BaseModel, Field

from app.data_access.protocols import Category


class AskRequest(BaseModel):
    user_id: str = Field(..., examples=["u1"])
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        examples=["My HRV dropped and my CNS feels fried. How should I adjust today's heavy leg day?"],
    )
    category: Category | None = Field(None, description="Restrict retrieval to one protocol category")


class Source(BaseModel):
    protocol_id: str
    title: str
    category: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
