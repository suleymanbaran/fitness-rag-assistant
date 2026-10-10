from functools import lru_cache
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import authorize, current_user_id
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.integrations.common import IntegrationError
from app.integrations.service import (
    PROVIDERS,
    Integrations,
    Provider,
    authorization_url,
    build_integrations,
    complete_fatsecret,
    complete_google,
    get_account,
    list_accounts,
    sync_user,
)
from app.schemas import USER_ID_PATTERN, ConnectResponse, IntegrationStatus, SyncResultOut

router = APIRouter(tags=["integrations"])


@lru_cache
def _integrations() -> Integrations:
    return build_integrations(get_settings())


def get_integrations() -> Integrations:
    # One shared instance: it holds the pending FatSecret request tokens between connect and callback.
    return _integrations()


def _require_user(db: Session, user_id: str) -> None:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")


@router.get("/users/{user_id}/integrations", response_model=list[IntegrationStatus])
def integration_status(
    user_id: str,
    db: Session = Depends(get_db),
    current: str | None = Depends(current_user_id),
    integrations: Integrations = Depends(get_integrations),
) -> list[IntegrationStatus]:
    authorize(user_id, current)
    accounts = {a.provider: a for a in list_accounts(db, user_id)}
    return [
        IntegrationStatus(
            provider=provider,
            configured=integrations.configured(provider),
            connected=provider in accounts,
            last_synced_at=accounts[provider].last_synced_at if provider in accounts else None,
            last_error=accounts[provider].last_error if provider in accounts else None,
        )
        for provider in PROVIDERS
    ]


@router.post("/users/{user_id}/integrations/{provider}/connect", response_model=ConnectResponse)
def connect(
    provider: Provider,
    user_id: str = Path(..., pattern=USER_ID_PATTERN),
    db: Session = Depends(get_db),
    current: str | None = Depends(current_user_id),
    integrations: Integrations = Depends(get_integrations),
) -> ConnectResponse:
    """Returns the provider's consent page URL. The browser goes there, then back to the callback."""
    authorize(user_id, current)
    _require_user(db, user_id)
    if not integrations.configured(provider):
        raise HTTPException(status_code=503, detail=f"{provider} is not configured on the server (see README)")
    try:
        return ConnectResponse(authorization_url=authorization_url(integrations, provider, user_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/users/{user_id}/integrations/{provider}", status_code=204)
def disconnect(
    provider: Provider,
    user_id: str,
    db: Session = Depends(get_db),
    current: str | None = Depends(current_user_id),
) -> None:
    authorize(user_id, current)
    if account := get_account(db, user_id, provider):
        db.delete(account)
        db.commit()


@router.post("/users/{user_id}/sync", response_model=list[SyncResultOut])
def sync(
    user_id: str,
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    current: str | None = Depends(current_user_id),
    integrations: Integrations = Depends(get_integrations),
) -> list[SyncResultOut]:
    authorize(user_id, current)
    _require_user(db, user_id)
    return [SyncResultOut(**vars(r)) for r in sync_user(db, integrations, user_id, days)]


# The callbacks are opened by the user's browser, coming back from the provider's consent page, so
# they carry no API token. They are protected instead by the encrypted, expiring `state` (Google) and
# the server-side pending request token (FatSecret), both of which bind the callback to one user.


def _back_to_ui(**params: str) -> RedirectResponse:
    return RedirectResponse(f"{get_settings().ui_url}?{urlencode(params)}", status_code=303)


@router.get("/integrations/google/callback", include_in_schema=False)
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    integrations: Integrations = Depends(get_integrations),
) -> RedirectResponse:
    if error or not code or not state:
        return _back_to_ui(integration_error=f"Google: {error or 'missing code'}")
    if not integrations.configured("google"):
        return _back_to_ui(integration_error="Google is not configured on the server")
    try:
        complete_google(db, integrations, code, state)
    except IntegrationError as exc:
        return _back_to_ui(integration_error=str(exc))
    return _back_to_ui(connected="google")


@router.get("/integrations/fatsecret/callback", include_in_schema=False)
def fatsecret_callback(
    oauth_token: str | None = None,
    oauth_verifier: str | None = None,
    db: Session = Depends(get_db),
    integrations: Integrations = Depends(get_integrations),
) -> RedirectResponse:
    if not oauth_token or not oauth_verifier:
        return _back_to_ui(integration_error="FatSecret: access was not approved")
    if not integrations.configured("fatsecret"):
        return _back_to_ui(integration_error="FatSecret is not configured on the server")
    try:
        complete_fatsecret(db, integrations, oauth_token, oauth_verifier)
    except IntegrationError as exc:
        return _back_to_ui(integration_error=str(exc))
    return _back_to_ui(connected="fatsecret")
