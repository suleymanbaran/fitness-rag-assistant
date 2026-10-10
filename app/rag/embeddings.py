from openai import OpenAI


class Embedder:
    def __init__(self, client: OpenAI, model: str) -> None:
        self.client = client
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        # One request for the whole batch: far fewer round trips than one call per text.
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
