"""
Google Health OAuth router.

Endpoints:
  POST   /api/auth/google/intent     — Exchange Vita JWT for a short-lived nonce (called by frontend BEFORE redirect)
  GET    /api/auth/google             — Initiate OAuth: read nonce from session, redirect to Google
  GET    /api/auth/google/callback   — Receive OAuth code, exchange for tokens, persist, redirect to frontend
  GET    /api/auth/google/status     — Return connection status for the current Vita user
  POST   /api/auth/google/sync       — On-demand Google Fit data sync
  DELETE /api/auth/google/disconnect — Revoke and delete stored tokens
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.encryption import decrypt, encrypt
from app.core.security import decode_token
from app.database import get_db
from app.models.google_health_token import GoogleHealthToken
from app.models.user import User
from app.schemas.google_health import GoogleHealthStatusOut, GoogleHealthSyncOut
from app.services.google_fit_service import sync_google_fit

# Allow HTTP in development only — must NOT be set in production
if settings.APP_ENV == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Relax token scope checks — Google Fit frequently expands scopes dynamically
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

router = APIRouter(
    prefix="/auth/google",
    tags=["Google Health"],
)

# ── OAuth scopes ──────────────────────────────────────────────────────────────
# Google Fit REST API scopes — web-accessible, populated by Fitbit Charge 6 via Google Health Connect.
# NOTE: If Google Fit REST API is retired, swap these scopes and update google_fit_service.py only.
GOOGLE_SCOPES = [
    "openid",
    "email",
    # Google Health API (v4 - Fitbit & Health Connect successor)
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.location.readonly",
    # Google Fit API (legacy compatibility)
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.oxygen_saturation.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.body_temperature.read",
    "https://www.googleapis.com/auth/fitness.location.read",
]

# ── Frontend redirect after successful connection ──────────────────────────────
_FRONTEND_SUCCESS_URL = "https://somachukwu.github.io/vitality/profile.html?google_connected=1"
_FRONTEND_ERROR_URL   = "https://somachukwu.github.io/vitality/profile.html?google_error=1"


def _build_flow(state: str | None = None) -> Flow:
    """Build a google-auth-oauthlib Flow from config settings."""
    return Flow.from_client_config(
        {
            "web": {
                "client_id":     settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
                "token_uri":     "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=GOOGLE_SCOPES,
        state=state,
    )


# ── 1. Intent endpoint ────────────────────────────────────────────────────────
@router.post("/intent", status_code=200)
def google_intent(
    current_user: User = Depends(get_current_user),
):
    """
    Called by the frontend (with JWT in Authorization header) BEFORE redirecting to Google.
    Generates a secure, short-lived signed connect token.
    """
    from jose import jwt
    # Create a short-lived token (expires in 5 minutes)
    payload = {
        "user_id": current_user.id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5)
    }
    connect_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {"connect_token": connect_token}


# ── 2. Initiation endpoint ────────────────────────────────────────────────────
@router.get("")
def google_auth(connect_token: str):
    """
    Decodes the connect_token, extracts user_id, starts the Google OAuth flow,
    and encodes the user_id and code_verifier into the OAuth 'state' parameter.
    """
    from jose import jwt
    try:
        payload = jwt.decode(connect_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload["user_id"]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired connection request. Please try again.",
        )

    flow = _build_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",   # always prompt so we always get a refresh_token
    )

    # Encode user_id, code_verifier, and state into the Google 'state' parameter
    # as a signed JWT that expires in 15 minutes.
    state_payload = {
        "user_id": user_id,
        "code_verifier": flow.code_verifier,
        "csrf_state": state,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
    }
    signed_state = jwt.encode(state_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    # Re-build the authorization URL replacing the state with our signed state
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    u = urlparse(authorization_url)
    q = parse_qs(u.query)
    q["state"] = [signed_state]
    new_query = urlencode(q, doseq=True)
    authorization_url = urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))

    return RedirectResponse(url=authorization_url)


# ── 3. Callback endpoint ──────────────────────────────────────────────────────
@router.get("/callback")
def google_auth_callback(request: Request, state: str, db: Session = Depends(get_db)):
    """
    Receives the OAuth code from Google after user consent.
    Validates state (CSRF), exchanges code for tokens, encrypts and persists them.
    Redirects the browser to the frontend profile page with ?google_connected=1.
    """
    from jose import jwt
    import logging
    logger = logging.getLogger(__name__)

    try:
        payload = jwt.decode(state, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        stored_user_id = payload["user_id"]
        code_verifier  = payload.get("code_verifier")
    except Exception as exc:
        logger.error("OAuth state JWT decode failed: %s", exc)
        return RedirectResponse(url=_FRONTEND_ERROR_URL)

    try:
        flow = _build_flow(state=state)
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        if code_verifier:
            flow.code_verifier = code_verifier
        
        # Replace 127.0.0.1 with localhost in request URL to match GOOGLE_REDIRECT_URI precisely
        req_url = str(request.url)
        if "127.0.0.1:8000" in req_url:
            req_url = req_url.replace("127.0.0.1:8000", "localhost:8000")
        if settings.GOOGLE_REDIRECT_URI.startswith("https://") and req_url.startswith("http://"):
            req_url = req_url.replace("http://", "https://", 1)
            
        flow.fetch_token(authorization_response=req_url)
    except Exception as exc:
        logger.error("OAuth flow fetch_token failed: %s", exc)
        return RedirectResponse(url=_FRONTEND_ERROR_URL)

    credentials = flow.credentials

    # Fetch the Google account email from the ID token or userinfo endpoint
    google_email = None
    try:
        import requests as req
        userinfo = req.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10,
        ).json()
        google_email = userinfo.get("email")
    except Exception:
        pass  # non-fatal — email display is cosmetic

    # Determine token expiry (Google tokens typically expire in 1 hour)
    token_expiry = None
    if credentials.expiry:
        token_expiry = credentials.expiry.replace(tzinfo=None)
    else:
        token_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    # Upsert — if user already has a token row, overwrite it (reconnect scenario)
    token_row = db.query(GoogleHealthToken).filter(
        GoogleHealthToken.user_id == stored_user_id
    ).first()

    if token_row:
        token_row.access_token  = encrypt(credentials.token)
        token_row.refresh_token = encrypt(credentials.refresh_token) if credentials.refresh_token else token_row.refresh_token
        token_row.token_expiry  = token_expiry
        token_row.scopes        = list(credentials.scopes or GOOGLE_SCOPES)
        token_row.google_email  = google_email
        token_row.is_active     = True
    else:
        token_row = GoogleHealthToken(
            user_id=stored_user_id,
            google_email=google_email,
            access_token=encrypt(credentials.token),
            refresh_token=encrypt(credentials.refresh_token) if credentials.refresh_token else None,
            token_expiry=token_expiry,
            scopes=list(credentials.scopes or GOOGLE_SCOPES),
            is_active=True,
        )
        db.add(token_row)

    db.commit()

    return RedirectResponse(url=_FRONTEND_SUCCESS_URL)


# ── 4. Status endpoint ────────────────────────────────────────────────────────
@router.get("/status", response_model=GoogleHealthStatusOut)
def google_health_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the Google Health connection status for the authenticated Vita user."""
    token_row = db.query(GoogleHealthToken).filter(
        GoogleHealthToken.user_id == current_user.id,
        GoogleHealthToken.is_active == True,
    ).first()

    if not token_row:
        return GoogleHealthStatusOut(connected=False)

    return GoogleHealthStatusOut(
        connected=True,
        google_email=token_row.google_email,
        last_synced_at=token_row.last_synced_at,
    )


# ── 5. On-demand sync endpoint ────────────────────────────────────────────────
@router.post("/sync", response_model=GoogleHealthSyncOut)
def google_health_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Triggers an on-demand Google Fit data sync for the last 24 hours.
    Inserts new Vitals rows and SleepSession rows.
    Weight is never synced from Google Fit — it comes from the smart scale only.
    """
    result = sync_google_fit(user_id=current_user.id, db=db, hours_back=24)
    return GoogleHealthSyncOut(
        synced_count=result["synced_count"],
        sleep_sessions_synced=result["sleep_sessions_synced"],
        message=f"Synced {result['synced_count']} vitals data points and {result['sleep_sessions_synced']} sleep session(s).",
    )


# ── 6. Disconnect endpoint ────────────────────────────────────────────────────
@router.delete("/disconnect", status_code=204)
def google_health_disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Removes the stored Google Health token for the current user.
    Also attempts to revoke the token with Google (best-effort).
    """
    token_row = db.query(GoogleHealthToken).filter(
        GoogleHealthToken.user_id == current_user.id
    ).first()

    if not token_row:
        raise HTTPException(status_code=404, detail="No Google Health connection found.")

    # Best-effort revocation with Google
    try:
        access_token = decrypt(token_row.access_token)
        import requests as req
        req.post(
            "https://oauth2.googleapis.com/revoke",
            params={"token": access_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=5,
        )
    except Exception:
        pass  # local deletion proceeds regardless

    db.delete(token_row)
    db.commit()
