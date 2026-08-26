from datetime import datetime, timedelta, timezone, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_device_from_api_key
from app.database import get_db
from app.models.device import Device
from app.models.user import User
from app.models.vitals import Vitals
from app.models.google_health_token import GoogleHealthToken
from app.schemas.vitals import (
    VitalsIngest, VitalsLatestOut, VitalsOut,
    VitalsDailySummary, SyncAllOut,
)

router = APIRouter(prefix="/vitals", tags=["vitals"])

# ── Metrics that reset daily (summed/maxed per day) ──────────────────────────
_DAILY_AGGREGATE_FIELDS = {"steps", "calories_burned", "distance_km", "active_minutes"}

# ── Metrics that are point-in-time (latest reading wins) ─────────────────────
_POINT_IN_TIME_FIELDS = {"heart_rate", "spo2", "temperature", "weight"}


@router.post("/ingest", response_model=VitalsOut, status_code=201)
def ingest_vitals(
    body: VitalsIngest,
    device: Device = Depends(get_device_from_api_key),
    db: Session = Depends(get_db),
):
    """ESP32 calls this endpoint to push sensor readings.

    Saves a new vitals row (time-series history) AND updates the user's
    profile with the latest sensor values so the app always shows current
    real-world data.
    """
    now = datetime.now(timezone.utc)

    # ── 1. Insert a new vitals record (preserves full history) ──────────
    record = Vitals(
        user_id=device.user_id,
        device_id=device.id,
        heart_rate=body.heart_rate,
        spo2=body.spo2,
        temperature=body.temperature,
        humidity=body.humidity,
        weight=body.weight,
        steps=body.steps,
        recorded_at=body.recorded_at or now,
    )
    db.add(record)

    # ── 2. Sync user profile with latest sensor readings ────────────────
    # Only update fields the sensor actually provided (non-None values).
    # This keeps the user's profile current without overwriting manually
    # entered data with stale NaN/null readings.
    user = db.get(User, device.user_id)
    if user is not None:
        if body.weight is not None:
            user.weight = body.weight          # station scale → profile weight

    # ── 3. Stamp device last-seen ────────────────────────────────────────
    device.last_seen = now

    db.commit()
    db.refresh(record)
    return record


def _build_latest_vitals(user: User, db: Session) -> VitalsLatestOut:
    """Build the latest vitals snapshot with proper today-only daily metrics.

    Point-in-time metrics (HR, SpO₂, temp, weight):
        → latest non-null value from ANY date (most recent reading).

    Daily aggregate metrics (steps, calories, distance, active_minutes):
        → today's values ONLY — yesterday's steps must never bleed into today.
        → treats 0 the same as None to prevent ESP32 zeros from overriding
          Google Health's real values.
    """
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )

    # Fetch recent records for point-in-time coalescing
    recent_records = (
        db.query(Vitals)
        .filter(Vitals.user_id == user.id)
        .order_by(Vitals.recorded_at.desc())
        .limit(30)
        .all()
    )
    if not recent_records:
        raise HTTPException(status_code=404, detail="No vitals recorded yet")

    latest = recent_records[0]
    out = VitalsLatestOut.model_validate(latest)
    if latest.device:
        out.device_name = latest.device.device_name

    # ── Point-in-time: coalesce from recent history (any date) ──────────
    for field in _POINT_IN_TIME_FIELDS:
        if getattr(out, field, None) is None:
            for rec in recent_records[1:]:
                val = getattr(rec, field, None)
                if val is not None:
                    setattr(out, field, val)
                    break

    # Fall back to profile weight if not present in vitals table
    if out.weight is None and user.weight is not None:
        out.weight = user.weight

    # ── Daily aggregates: TODAY only ────────────────────────────────────
    # Reset all daily fields first, then fill from today's records
    for field in _DAILY_AGGREGATE_FIELDS:
        setattr(out, field, None)

    today_records = (
        db.query(Vitals)
        .filter(
            Vitals.user_id == user.id,
            Vitals.recorded_at >= today_start,
        )
        .order_by(Vitals.recorded_at.desc())
        .all()
    )

    for field in _DAILY_AGGREGATE_FIELDS:
        best = None
        for rec in today_records:
            val = getattr(rec, field, None)
            # Treat 0 as "no data" for daily aggregates — prevents ESP32
            # pushing steps=0 from overriding real Google Health step counts
            if val is not None and val > 0:
                if best is None or val > best:
                    best = val
        if best is not None:
            setattr(out, field, best)

    token_row = (
        db.query(GoogleHealthToken)
        .filter(GoogleHealthToken.user_id == user.id, GoogleHealthToken.is_active == True)
        .first()
    )
    if token_row:
        out.last_google_sync = token_row.last_synced_at

    return out


@router.get("/latest", response_model=VitalsLatestOut)
def get_latest_vitals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_latest_vitals(current_user, db)


@router.get("/history", response_model=list[VitalsDailySummary])
def get_vitals_history(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return vitals history grouped by calendar date.

    For each date:
      - Daily aggregates (steps, calories, distance): MAX across all sources
      - Point-in-time (HR, SpO₂, temp, weight): latest reading that day
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    records = (
        db.query(Vitals)
        .filter(
            Vitals.user_id == current_user.id,
            Vitals.recorded_at >= since,
        )
        .order_by(Vitals.recorded_at.asc())
        .all()
    )

    # Group records by calendar date
    by_date: dict[date, list[Vitals]] = {}
    for rec in records:
        d = rec.recorded_at.date()
        by_date.setdefault(d, []).append(rec)

    summaries = []
    for d in sorted(by_date.keys()):
        recs = by_date[d]

        # Daily aggregates: take the MAX non-zero value across all sources
        steps = max((r.steps or 0 for r in recs), default=0) or None
        cals = max((r.calories_burned or 0.0 for r in recs), default=0.0) or None
        dist = max((r.distance_km or 0.0 for r in recs), default=0.0) or None
        active = max((r.active_minutes or 0 for r in recs), default=0) or None

        # Point-in-time: latest non-null reading that day
        hr = temp = spo2 = weight = None
        for r in reversed(recs):  # most recent first
            if hr is None and r.heart_rate is not None:
                hr = r.heart_rate
            if spo2 is None and r.spo2 is not None:
                spo2 = r.spo2
            if temp is None and r.temperature is not None:
                temp = r.temperature
            if weight is None and r.weight is not None:
                weight = r.weight
            if all(v is not None for v in (hr, spo2, temp, weight)):
                break

        summaries.append(VitalsDailySummary(
            date=d,
            heart_rate=hr,
            spo2=spo2,
            temperature=temp,
            weight=weight,
            steps=steps,
            calories_burned=round(cals, 1) if cals else None,
            distance_km=round(dist, 2) if dist else None,
            active_minutes=active,
        ))

    return summaries


@router.post("/sync-all", response_model=SyncAllOut)
def sync_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-click sync: triggers Google Health sync, then returns fresh vitals.

    Called by the dashboard sync button so users get a single action that
    pulls latest data from Google AND refreshes the display.
    """
    from app.services.google_health_service import sync_google_health
    from app.models.google_health_token import GoogleHealthToken

    google_synced = False
    synced_count = 0
    sleep_sessions_synced = 0

    # Check if user has an active Google Health connection
    token_row = db.query(GoogleHealthToken).filter(
        GoogleHealthToken.user_id == current_user.id,
        GoogleHealthToken.is_active == True,
    ).first()

    if token_row:
        result = sync_google_health(
            user_id=current_user.id, db=db, hours_back=24
        )
        google_synced = True
        synced_count = result["synced_count"]
        sleep_sessions_synced = result["sleep_sessions_synced"]

    # Build fresh vitals after sync
    try:
        vitals = _build_latest_vitals(current_user, db)
    except HTTPException:
        vitals = None

    return SyncAllOut(
        google_synced=google_synced,
        synced_count=synced_count,
        sleep_sessions_synced=sleep_sessions_synced,
        vitals=vitals,
    )
