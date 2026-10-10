"""Load the demo users from data/users.json into Postgres. Safe to run repeatedly.

Usage: python -m scripts.seed
"""

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.data_access.biometrics import upsert_daily_metrics
from app.db.models import User
from app.db.session import get_sessionmaker

USERS_PATH = Path(__file__).resolve().parents[1] / "data" / "users.json"


def seed_demo_users(db: Session) -> int:
    raw_users = json.loads(USERS_PATH.read_text())
    for raw in raw_users:
        db.merge(
            User(
                id=raw["user_id"],
                name=raw["name"],
                age=raw["age"],
                weight_kg=raw["weight_kg"],
                goal=raw["goal"],
            )
        )
        db.flush()
        for day in raw["days"]:
            metrics = {k: v for k, v in day.items() if k != "date"}
            upsert_daily_metrics(db, raw["user_id"], date.fromisoformat(day["date"]), source="seed", **metrics)
    db.commit()
    return len(raw_users)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Seed even when AUTH_ENABLED=true")
    args = parser.parse_args()
    if get_settings().auth_enabled and not args.force:
        parser.error("AUTH_ENABLED=true looks like a deployment; demo users do not belong there (use --force)")

    with get_sessionmaker()() as db:
        count = seed_demo_users(db)
    print(f"Seeded {count} demo users")


if __name__ == "__main__":
    main()
