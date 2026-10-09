"""Insert a demo user and biometrics for local testing."""

from datetime import date, timedelta
from uuid import uuid4

from app.database import Base, SessionLocal, engine
from app.models.daily_biometrics import DailyBiometrics
from app.models.user import User


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = User(
            id=uuid4(),
            email="demo@fitness.local",
            display_name="Demo Lifter",
        )
        db.add(user)
        db.flush()

        today = date.today()
        samples = [
            (today - timedelta(days=1), 62.0, 78, 54, 82.5, 2800),
            (today, 52.7, 61, 58, 82.3, 2400),
        ]
        for recorded_on, hrv, sleep, rhr, weight, kcal in samples:
            db.add(
                DailyBiometrics(
                    user_id=user.id,
                    recorded_on=recorded_on,
                    hrv_ms=hrv,
                    sleep_score=sleep,
                    resting_heart_rate_bpm=rhr,
                    weight_kg=weight,
                    calorie_intake_kcal=kcal,
                )
            )
        db.commit()
        print(f"Seeded user_id={user.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
