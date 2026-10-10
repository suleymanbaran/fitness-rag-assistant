import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

PROTOCOLS_PATH = Path(__file__).resolve().parents[2] / "data" / "protocols.json"

Category = Literal["recovery", "training", "sleep", "nutrition", "safety"]


class Protocol(BaseModel):
    id: str
    title: str
    category: Category
    text: str


def load_protocols() -> list[Protocol]:
    raw = json.loads(PROTOCOLS_PATH.read_text())
    return [Protocol.model_validate(item) for item in raw]
