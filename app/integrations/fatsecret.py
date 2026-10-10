"""FatSecret Platform API: daily calories from the user's food diary.

Reading a member's diary requires 3-legged OAuth 1.0 (FatSecret's OAuth 2.0 cannot act for a user).
Docs: https://platform.fatsecret.com/docs/guides/authentication/oauth1/three-legged
"""

from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode

import httpx
from oauthlib.oauth1 import SIGNATURE_TYPE_BODY, SIGNATURE_TYPE_QUERY, Client

from app.integrations.common import IntegrationError, ReauthRequired, request_with_retry

REQUEST_TOKEN_URL = "https://authentication.fatsecret.com/oauth/request_token"
AUTHORIZE_URL = "https://authentication.fatsecret.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://authentication.fatsecret.com/oauth/access_token"
FOOD_ENTRIES_URL = "https://platform.fatsecret.com/rest/food-entries/v2"
EPOCH = date(1970, 1, 1)
# FatSecret error codes meaning the stored access token is no longer valid.
INVALID_TOKEN_CODES = {9, 13}


class FatSecretClient:
    provider = "fatsecret"

    def __init__(self, consumer_key: str, consumer_secret: str, http: httpx.Client | None = None) -> None:
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.http = http or httpx.Client(timeout=20)

    def start_authorization(self, callback_url: str) -> tuple[str, str, str]:
        """Step 1-2: get a request token. Returns (URL to send the user to, request token, request secret)."""
        # FatSecret verifies this POST against the form body. The same signature in the
        # query string is rejected as invalid.
        client = Client(
            self.consumer_key,
            client_secret=self.consumer_secret,
            callback_uri=callback_url,
            signature_type=SIGNATURE_TYPE_BODY,
        )
        uri, _, body = client.sign(
            REQUEST_TOKEN_URL,
            http_method="POST",
            body="",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = request_with_retry(
            self.http,
            "POST",
            uri,
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.is_error:
            raise IntegrationError(f"FatSecret request token failed ({response.status_code}): {response.text[:120]}")
        values = dict(parse_qsl(response.text))
        token, secret = values["oauth_token"], values["oauth_token_secret"]
        return f"{AUTHORIZE_URL}?{urlencode({'oauth_token': token})}", token, secret

    def finish_authorization(self, request_token: str, request_secret: str, verifier: str) -> tuple[str, str]:
        """Step 3: exchange the approved request token for the member's access token and secret."""
        client = Client(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=request_token,
            resource_owner_secret=request_secret,
            verifier=verifier,
            signature_type=SIGNATURE_TYPE_QUERY,
        )
        uri, _, _ = client.sign(ACCESS_TOKEN_URL, http_method="GET")
        response = request_with_retry(self.http, "GET", uri)
        if response.is_error:
            raise IntegrationError(f"FatSecret access token failed ({response.status_code}): {response.text[:120]}")
        values = dict(parse_qsl(response.text))
        return values["oauth_token"], values["oauth_token_secret"]

    def fetch_days(self, token: str, secret: str, start: date, end: date) -> dict[date, dict]:
        """Total calories per day. Days with no diary entries are left out: not logged is not zero eaten."""
        days = {}
        day = start
        while day <= end:
            calories = self._day_calories(token, secret, day)
            if calories is not None:
                days[day] = {"calories_kcal": calories}
            day += timedelta(days=1)
        return days

    def _day_calories(self, token: str, secret: str, day: date) -> int | None:
        client = Client(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=token,
            resource_owner_secret=secret,
            signature_type=SIGNATURE_TYPE_QUERY,
        )
        query = urlencode({"date": (day - EPOCH).days, "format": "json"})
        uri, _, _ = client.sign(f"{FOOD_ENTRIES_URL}?{query}", http_method="GET")
        response = request_with_retry(self.http, "GET", uri)
        if response.is_error:
            raise IntegrationError(f"FatSecret food diary request failed ({response.status_code})")
        return parse_food_entries(response.json())


def parse_food_entries(body: dict) -> int | None:
    # FatSecret reports errors with HTTP 200 and an "error" object.
    if error := body.get("error"):
        code, message = int(error.get("code", 0)), error.get("message", "unknown error")
        if code in INVALID_TOKEN_CODES:
            raise ReauthRequired("FatSecret rejected the stored login. Connect FatSecret again.")
        raise IntegrationError(f"FatSecret error {code}: {message}")

    entries = (body.get("food_entries") or {}).get("food_entry") or []
    if isinstance(entries, dict):  # a single entry is returned as an object, not a list
        entries = [entries]
    if not entries:
        return None
    return round(sum(float(e.get("calories") or 0) for e in entries))
