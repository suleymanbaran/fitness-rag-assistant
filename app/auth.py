import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_db


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user_id(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> str | None:
    """The authenticated user's ID, or None when auth is disabled (local use)."""
    if not settings.auth_enabled:
        return None
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    user_id = None
    if scheme.lower() == "bearer" and token:
        user_id = db.scalar(select(User.id).where(User.api_token_hash == hash_token(token)))
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def authorize(user_id: str, current: str | None) -> None:
    if current is not None and current != user_id:
        raise HTTPException(status_code=403, detail="You can only access your own data")


class RateLimiter:
    """Sliding-window limit per key, kept in memory. Correct for a single API process only."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = int(self.window - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many questions, try again shortly",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)


ask_limiter = RateLimiter()


def get_ask_limiter() -> RateLimiter:
    return ask_limiter
