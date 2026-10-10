"""Create (or reset) a user's API token, creating the user if needed. Prints the token once.

Usage: python -m scripts.issue_token me --name "Suleyman"
Only the token's SHA-256 is stored, so a lost token cannot be recovered: issue a new one.
"""

import argparse
import re

from app.auth import hash_token, new_token
from app.db.models import User
from app.db.session import get_sessionmaker
from app.schemas import USER_ID_PATTERN


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("user_id")
    parser.add_argument("--name", help="Required when the user does not exist yet")
    args = parser.parse_args()

    if not re.fullmatch(USER_ID_PATTERN, args.user_id):
        parser.error("user_id may contain only lowercase letters, digits, - and _")

    with get_sessionmaker()() as db:
        user = db.get(User, args.user_id)
        if user is None:
            if not args.name:
                parser.error(f"User {args.user_id} does not exist; pass --name to create it")
            user = User(id=args.user_id, name=args.name, goal="general_fitness")
            db.add(user)
        token = new_token()
        user.api_token_hash = hash_token(token)
        db.commit()

    print(f"Token for {args.user_id} (shown once, any previous token is now invalid):\n{token}")


if __name__ == "__main__":
    main()
