from typing import TypedDict


class ProtocolDocument(TypedDict):
    id: str
    title: str
    category: str
    content: str
    tags: list[str]


# MVP seed corpus — replace or extend via admin ingest in production.
RECOVERY_PROTOCOLS: list[ProtocolDocument] = [
    {
        "id": "hrv-autoregulation-001",
        "title": "HRV-Guided Training Autoregulation",
        "category": "recovery",
        "content": (
            "When HRV drops more than ~10% below a 7-day rolling baseline, reduce "
            "session RPE by 1–2 points or swap heavy compounds for submaximal "
            "technique work. Prioritize sleep, hydration, and low-intensity "
            "cardiac output (20–30 min Zone 2) before returning to high neural load."
        ),
        "tags": ["hrv", "autoregulation", "cns", "deload"],
    },
    {
        "id": "cns-fatigue-legs-002",
        "title": "CNS Fatigue Management on Lower-Body Days",
        "category": "training",
        "content": (
            "Signs of CNS fatigue include elevated resting HR, poor sleep, and "
            "subjective 'heaviness.' For planned heavy leg days, reduce working "
            "sets by 30–40%, cap intensity at RPE 7–8, and extend rest intervals "
            "to 3–5 minutes. Consider unilateral work and tempo squats instead of "
            "max-effort bilateral loading."
        ),
        "tags": ["cns", "legs", "squat", "fatigue"],
    },
    {
        "id": "sleep-debt-003",
        "title": "Sleep Debt and Resistance Training",
        "category": "sleep",
        "content": (
            "Sleep scores below 70 or less than 6 hours sleep correlate with "
            "impaired force production and slower recovery. Avoid novel 1RM attempts; "
            "use volume landmarks at the low end of MEV and emphasize mobility, "
            "breathing drills, and early bedtime the following night."
        ),
        "tags": ["sleep", "recovery", "volume"],
    },
    {
        "id": "hr-resting-004",
        "title": "Elevated Resting Heart Rate Protocol",
        "category": "biometrics",
        "content": (
            "Resting HR 5–10 bpm above baseline often indicates incomplete recovery "
            "or illness onset. Defer high-impact plyometrics and maximal lifts; "
            "monitor for 24–48h. If elevated HR persists with HRV suppression, "
            "implement a full deload week at 50–60% of typical volume."
        ),
        "tags": ["resting_hr", "deload", "illness"],
    },
    {
        "id": "nutrition-recovery-005",
        "title": "Calorie and Protein Support During High Stress",
        "category": "nutrition",
        "content": (
            "Under-fueling amplifies HRV suppression. During high training stress, "
            "maintain protein at 1.6–2.2 g/kg and avoid aggressive deficits. "
            "Carbohydrate availability around training supports glycogen and "
            "parasympathetic recovery; prioritize post-session meals within 2 hours."
        ),
        "tags": ["calories", "protein", "nutrition", "recovery"],
    },
    {
        "id": "active-recovery-006",
        "title": "Active Recovery Session Template",
        "category": "recovery",
        "content": (
            "On low-readiness days, use 20–40 minutes of walking, cycling, or "
            "swimming at conversational intensity, plus 10 minutes of mobility "
            "for hips and thoracic spine. Avoid failure training; goal is "
            "increased blood flow without additional CNS cost."
        ),
        "tags": ["active_recovery", "mobility", "zone2"],
    },
]
