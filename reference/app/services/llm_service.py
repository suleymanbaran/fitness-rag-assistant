from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings
from app.models.daily_biometrics import DailyBiometrics
from app.schemas.analyze import RetrievedProtocol

SYSTEM_PROMPT = """You are an evidence-informed strength and recovery coach.
Use ONLY the supplied biometric data and retrieved protocol excerpts.
If data is missing, state assumptions clearly and recommend conservative adjustments.
Be specific about session changes (volume, intensity, exercise swaps, recovery).
Do not diagnose medical conditions; suggest professional care when red flags appear."""


@dataclass(frozen=True)
class LLMService:
    settings: Settings
    chat: ChatOpenAI

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> LLMService:
        cfg = settings or get_settings()
        chat = ChatOpenAI(
            model=cfg.openai_model,
            api_key=cfg.openai_api_key or None,
            temperature=0.3,
        )
        return cls(settings=cfg, chat=chat)

    @staticmethod
    def _format_biometrics(biometrics: list[DailyBiometrics]) -> str:
        if not biometrics:
            return "No biometric records on file."

        blocks: list[str] = []
        for row in biometrics:
            blocks.append(
                "\n".join(
                    [
                        f"Date: {row.recorded_on}",
                        f"  HRV (ms): {row.hrv_ms if row.hrv_ms is not None else 'n/a'}",
                        f"  Sleep score: {row.sleep_score if row.sleep_score is not None else 'n/a'}",
                        f"  Resting HR (bpm): {row.resting_heart_rate_bpm if row.resting_heart_rate_bpm is not None else 'n/a'}",
                        f"  Weight (kg): {row.weight_kg if row.weight_kg is not None else 'n/a'}",
                        f"  Calorie intake (kcal): {row.calorie_intake_kcal if row.calorie_intake_kcal is not None else 'n/a'}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _format_protocols(protocols: list[RetrievedProtocol]) -> str:
        if not protocols:
            return "No matching protocols retrieved."
        parts: list[str] = []
        for idx, proto in enumerate(protocols, start=1):
            parts.append(
                f"{idx}. [{proto.category}] {proto.title}\n{proto.content}"
            )
        return "\n\n".join(parts)

    def generate_recommendation(
        self,
        user_query: str,
        biometrics: list[DailyBiometrics],
        protocols: list[RetrievedProtocol],
    ) -> str:
        human_content = (
            f"User question:\n{user_query}\n\n"
            f"Recent biometrics (newest first):\n{self._format_biometrics(biometrics)}\n\n"
            f"Retrieved protocols:\n{self._format_protocols(protocols)}\n\n"
            "Provide a concise, actionable plan for today including warm-up, main lifts, "
            "and recovery steps."
        )
        response = self.chat.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=human_content),
            ]
        )
        content = response.content
        if isinstance(content, str):
            return content
        return str(content)
