"""Sync connected providers for every user (or one). Run on a schedule, e.g. cron every 3 hours.

Usage: python -m scripts.sync [--user-id me] [--days 3]
"""

import argparse

from sqlalchemy import select

from app.config import get_settings
from app.db.models import IntegrationAccount
from app.db.session import get_sessionmaker
from app.integrations.service import build_integrations, sync_user


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id")
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()

    integrations = build_integrations(get_settings())
    with get_sessionmaker()() as db:
        user_ids = [args.user_id] if args.user_id else sorted(set(db.scalars(select(IntegrationAccount.user_id))))
        for user_id in user_ids:
            for result in sync_user(db, integrations, user_id, args.days):
                status = f"error: {result.error}" if result.error else f"{result.days_updated} days updated"
                print(f"{user_id} {result.provider}: {status}")


if __name__ == "__main__":
    main()
