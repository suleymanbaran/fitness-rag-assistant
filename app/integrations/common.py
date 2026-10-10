import json
import time

import httpx
from cryptography.fernet import Fernet, InvalidToken

RETRY_STATUSES = {429, 500, 502, 503, 504}
BACKOFF_SECONDS = 1.0


class IntegrationError(Exception):
    """A provider call failed in a way the user should see (shown as the connection's last error)."""


class ReauthRequired(IntegrationError):
    """The stored tokens no longer work; the user has to connect the provider again."""


class TokenCipher:
    """Symmetric encryption for OAuth tokens at rest, and tamper-proof, expiring OAuth `state` values."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise ReauthRequired("The stored login cannot be decrypted (was TOKEN_ENCRYPTION_KEY changed?). Connect again.") from exc

    def make_state(self, payload: dict) -> str:
        return self.encrypt(json.dumps(payload))

    def read_state(self, state: str, max_age_seconds: int = 600) -> dict:
        try:
            return json.loads(self._fernet.decrypt(state.encode(), ttl=max_age_seconds))
        except InvalidToken as exc:
            raise IntegrationError("The connection link expired or was tampered with. Try connecting again.") from exc


def request_with_retry(client: httpx.Client, method: str, url: str, retries: int = 2, **kwargs) -> httpx.Response:
    """Retries network errors, rate limits and 5xx with exponential backoff (honouring Retry-After)."""
    for attempt in range(retries + 1):
        last_attempt = attempt == retries
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if last_attempt:
                raise IntegrationError(f"Could not reach {httpx.URL(url).host}") from exc
            time.sleep(BACKOFF_SECONDS * 2**attempt)
            continue
        if response.status_code in RETRY_STATUSES and not last_attempt:
            retry_after = response.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else BACKOFF_SECONDS * 2**attempt
            time.sleep(min(delay, 30.0))
            continue
        return response
    raise AssertionError("unreachable")
