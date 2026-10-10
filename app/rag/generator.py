from openai import OpenAI


class Generator:
    def __init__(self, client: OpenAI, model: str, temperature: float = 0.2) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature

    def generate(self, messages: list[dict]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""
