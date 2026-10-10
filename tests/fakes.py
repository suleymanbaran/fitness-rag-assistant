from app.rag.demo import HashingEmbedder as FakeEmbedder

__all__ = ["FakeEmbedder", "FakeGenerator"]


class FakeGenerator:
    def __init__(self) -> None:
        self.last_messages: list[dict] | None = None

    def generate(self, messages: list[dict]) -> str:
        self.last_messages = messages
        return "Fake answer [rec-hrv-autoregulation]"
