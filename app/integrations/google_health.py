"""Google Health API (successor of the Fitbit Web API): daily HRV, resting heart rate and sleep.

Docs: https://developers.google.com/health
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.integrations.common import IntegrationError, ReauthRequired, request_with_retry

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DATA_TYPES_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
]


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime


class GoogleHealthClient:
    provider = "google"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, http: httpx.Client | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = http or httpx.Client(timeout=20)

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            # offline + consent: Google returns a refresh token, so syncing keeps working after the
            # one-hour access token expires.
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> OAuthTokens:
        return self._token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri})

    def refresh(self, refresh_token: str) -> OAuthTokens:
        tokens = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
        # Google usually omits the refresh token on refresh; the original one stays valid.
        return OAuthTokens(tokens.access_token, tokens.refresh_token or refresh_token, tokens.expires_at)

    def _token_request(self, data: dict) -> OAuthTokens:
        data |= {"client_id": self.client_id, "client_secret": self.client_secret}
        response = request_with_retry(self.http, "POST", TOKEN_URL, data=data)
        if response.status_code in (400, 401):
            # invalid_grant: the refresh token was revoked or expired (e.g. a test-mode app after 7 days).
            raise ReauthRequired("Google rejected the stored login. Connect Google Health again.")
        if response.is_error:
            raise IntegrationError(f"Google token request failed ({response.status_code})")
        body = response.json()
        return OAuthTokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            expires_at=datetime.now(UTC) + timedelta(seconds=int(body.get("expires_in", 3600))),
        )

    def fetch_days(self, access_token: str, start: date, end: date) -> dict[date, dict]:
        """Metrics per day from `start` to `end` inclusive, keyed by the user's local date."""
        after = (end + timedelta(days=1)).isoformat()
        hrv = self._list(
            access_token,
            "daily-heart-rate-variability",
            f'daily_heart_rate_variability.date >= "{start}" AND daily_heart_rate_variability.date < "{after}"',
        )
        rhr = self._list(
            access_token,
            "daily-resting-heart-rate",
            f'daily_resting_heart_rate.date >= "{start}" AND daily_resting_heart_rate.date < "{after}"',
        )
        sleep = self._list(
            access_token,
            "sleep",
            f'sleep.interval.civil_end_time >= "{start}" AND sleep.interval.civil_end_time < "{after}"',
        )

        days: dict[date, dict] = {}
        for day, value in parse_daily_hrv(hrv).items():
            days.setdefault(day, {})["hrv_ms"] = value
        for day, value in parse_resting_hr(rhr).items():
            days.setdefault(day, {})["resting_hr_bpm"] = value
        for day, value in parse_sleep_minutes(sleep).items():
            days.setdefault(day, {})["sleep_minutes"] = value
        return {day: values for day, values in days.items() if start <= day <= end}

    def _list(self, access_token: str, data_type: str, filter_expr: str) -> list[dict]:
        points: list[dict] = []
        params = {"filter": filter_expr}
        while True:
            response = request_with_retry(
                self.http,
                "GET",
                f"{DATA_TYPES_URL}/{data_type}/dataPoints",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 401:
                raise ReauthRequired("Google rejected the access token. Connect Google Health again.")
            if response.status_code == 403:
                raise IntegrationError(f"Google denied access to {data_type}. Approve all requested permissions.")
            if response.is_error:
                raise IntegrationError(f"Google Health {data_type} request failed ({response.status_code})")
            body = response.json()
            points.extend(body.get("dataPoints", []))
            if not body.get("nextPageToken"):
                return points
            params = {"filter": filter_expr, "pageToken": body["nextPageToken"]}


def _civil_date(value: dict) -> date:
    return date(value["year"], value["month"], value["day"])


def parse_daily_hrv(points: list[dict]) -> dict[date, float]:
    result = {}
    for point in points:
        data = point.get("dailyHeartRateVariability") or {}
        if "date" in data and data.get("averageHeartRateVariabilityMilliseconds") is not None:
            result[_civil_date(data["date"])] = round(float(data["averageHeartRateVariabilityMilliseconds"]), 1)
    return result


def parse_resting_hr(points: list[dict]) -> dict[date, int]:
    result = {}
    for point in points:
        data = point.get("dailyRestingHeartRate") or {}
        if "date" in data and data.get("beatsPerMinute") is not None:
            # 64-bit integers arrive as JSON strings.
            result[_civil_date(data["date"])] = int(data["beatsPerMinute"])
    return result


def parse_sleep_minutes(points: list[dict]) -> dict[date, int]:
    """Minutes asleep in the main sleep of each night, keyed by the local date the sleep ended."""
    best: dict[date, tuple[bool, int]] = {}
    for point in points:
        sleep = point.get("sleep") or {}
        minutes = (sleep.get("summary") or {}).get("minutesAsleep")
        interval = sleep.get("interval") or {}
        if minutes is None or "civilEndTime" not in interval:
            continue  # still processing, or no local time available
        day = _civil_date(interval["civilEndTime"]["date"])
        is_main = bool((sleep.get("metadata") or {}).get("mainSleep"))
        candidate = (is_main, int(minutes))
        # Prefer the session Google marks as main sleep; otherwise the longest one. Naps lose.
        if day not in best or candidate > best[day]:
            best[day] = candidate
    return {day: minutes for day, (_, minutes) in best.items()}
