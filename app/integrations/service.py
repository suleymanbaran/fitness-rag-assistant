"""Connecting providers, storing their tokens encrypted, and syncing their data into daily_biometrics."""

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.data_access.biometrics import upsert_daily_metrics
from app.db.models import IntegrationAccount
from app.integrations.common import IntegrationError, ReauthRequired, TokenCipher
from app.integrations.fatsecret import FatSecretClient
from app.integrations.google_health import GoogleHealthClient

Provider = Literal["google", "fatsecret"]
PROVIDERS: tuple[Provider, ...] = ("google", "fatsecret")


class PendingRequestTokens:
    """FatSecret request-token secrets between "connect" and the callback (OAuth 1.0 step 1 to 3).
    In memory with a short TTL: a restart mid-connect only means clicking Connect again."""

    def __init__(self, ttl_seconds: float = 600) -> None:
        self.ttl = ttl_seconds
        self._items: dict[str, tuple[float, str, str]] = {}
        self._lock = threading.Lock()

    def put(self, request_token: str, user_id: str, request_secret: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            self._items[request_token] = (now + self.ttl, user_id, request_secret)

    def pop(self, request_token: str) -> tuple[str, str]:
        with self._lock:
            expires, user_id, secret = self._items.pop(request_token, (0.0, "", ""))
        if expires < time.monotonic():
            raise IntegrationError("The FatSecret connection expired. Try connecting again.")
        return user_id, secret


@dataclass
class Integrations:
    cipher: TokenCipher | None
    google: GoogleHealthClient | None
    fatsecret: FatSecretClient | None
    public_api_url: str
    pending: PendingRequestTokens = field(default_factory=PendingRequestTokens)

    def configured(self, provider: Provider) -> bool:
        return self.cipher is not None and getattr(self, provider) is not None


def build_integrations(settings: Settings) -> Integrations:
    api = settings.public_api_url.rstrip("/")
    google = fatsecret = None
    if settings.google_client_id and settings.google_client_secret:
        google = GoogleHealthClient(
            settings.google_client_id, settings.google_client_secret, f"{api}/integrations/google/callback"
        )
    if settings.fatsecret_consumer_key and settings.fatsecret_consumer_secret:
        fatsecret = FatSecretClient(settings.fatsecret_consumer_key, settings.fatsecret_consumer_secret)
    cipher = TokenCipher(settings.token_encryption_key) if settings.token_encryption_key else None
    return Integrations(cipher=cipher, google=google, fatsecret=fatsecret, public_api_url=api)


def authorization_url(integrations: Integrations, provider: Provider, user_id: str) -> str:
    if provider == "google":
        state = integrations.cipher.make_state({"user_id": user_id, "provider": "google"})
        return integrations.google.authorization_url(state)
    url, request_token, request_secret = integrations.fatsecret.start_authorization(
        f"{integrations.public_api_url}/integrations/fatsecret/callback"
    )
    integrations.pending.put(request_token, user_id, request_secret)
    return url


def complete_google(db: Session, integrations: Integrations, code: str, state: str) -> str:
    payload = integrations.cipher.read_state(state)
    if payload.get("provider") != "google":
        raise IntegrationError("Invalid connection state")
    tokens = integrations.google.exchange_code(code)
    cipher = integrations.cipher
    _save_account(
        db,
        payload["user_id"],
        "google",
        access_token_enc=cipher.encrypt(tokens.access_token),
        refresh_token_enc=cipher.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        token_secret_enc=None,
        expires_at=tokens.expires_at,
    )
    return payload["user_id"]


def complete_fatsecret(db: Session, integrations: Integrations, request_token: str, verifier: str) -> str:
    user_id, request_secret = integrations.pending.pop(request_token)
    token, secret = integrations.fatsecret.finish_authorization(request_token, request_secret, verifier)
    cipher = integrations.cipher
    _save_account(
        db,
        user_id,
        "fatsecret",
        access_token_enc=cipher.encrypt(token),
        refresh_token_enc=None,
        token_secret_enc=cipher.encrypt(secret),
        expires_at=None,  # FatSecret OAuth 1.0 tokens do not expire
    )
    return user_id


def _save_account(db: Session, user_id: str, provider: Provider, **fields) -> None:
    account = get_account(db, user_id, provider) or IntegrationAccount(user_id=user_id, provider=provider)
    for name, value in fields.items():
        setattr(account, name, value)
    account.last_error = None
    db.add(account)
    db.commit()


def get_account(db: Session, user_id: str, provider: str) -> IntegrationAccount | None:
    return db.scalar(
        select(IntegrationAccount).where(IntegrationAccount.user_id == user_id, IntegrationAccount.provider == provider)
    )


def list_accounts(db: Session, user_id: str) -> list[IntegrationAccount]:
    return list(db.scalars(select(IntegrationAccount).where(IntegrationAccount.user_id == user_id)))


@dataclass(frozen=True)
class SyncResult:
    provider: str
    days_updated: int
    error: str | None = None
    reconnect: bool = False


def sync_user(db: Session, integrations: Integrations, user_id: str, days: int) -> list[SyncResult]:
    """Pull the last `days` days (today included) from every connected provider and upsert them.
    Re-running is safe: each provider only overwrites its own fields on each day."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    results = []
    for account in list_accounts(db, user_id):
        if not integrations.configured(account.provider):
            results.append(SyncResult(account.provider, 0, "Provider credentials are not configured on the server"))
            continue
        try:
            metrics = _fetch(account, integrations, start, end)
            for day, values in metrics.items():
                upsert_daily_metrics(db, user_id, day, source=account.provider, **values)
            account.last_synced_at = datetime.now(UTC)
            account.last_error = None
            results.append(SyncResult(account.provider, len(metrics)))
        except IntegrationError as exc:
            account.last_error = str(exc)[:300]
            results.append(SyncResult(account.provider, 0, str(exc), reconnect=isinstance(exc, ReauthRequired)))
        db.commit()
    return results


def _fetch(account: IntegrationAccount, integrations: Integrations, start: date, end: date) -> dict[date, dict]:
    cipher = integrations.cipher
    if account.provider == "google":
        if account.expires_at is None or account.expires_at <= datetime.now(UTC) + timedelta(minutes=1):
            if not account.refresh_token_enc:
                raise ReauthRequired("Google login expired. Connect Google Health again.")
            tokens = integrations.google.refresh(cipher.decrypt(account.refresh_token_enc))
            account.access_token_enc = cipher.encrypt(tokens.access_token)
            account.refresh_token_enc = cipher.encrypt(tokens.refresh_token)
            account.expires_at = tokens.expires_at
        return integrations.google.fetch_days(cipher.decrypt(account.access_token_enc), start, end)
    return integrations.fatsecret.fetch_days(
        cipher.decrypt(account.access_token_enc), cipher.decrypt(account.token_secret_enc), start, end
    )
