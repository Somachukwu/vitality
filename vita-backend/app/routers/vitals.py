from datetime import datetime, timedelta, timezone, date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_device_from_api_key
from app.database import get_db
from app.models.device import Device
from app.models.user import User
from app.models.vitals import Vitals
from app.models.sleep_session import SleepSession
from app.models.google_health_token import GoogleHealthToken
from app.schemas.vitals import (
    VitalsIngest, VitalsLatestOut, VitalsOut,
    VitalsDailySummary, SyncAllOut,
)

router = APIRouter(prefix="/vitals", tags=["vitals"])

# ── Metrics that reset daily (summed/maxed per day) ──────────────────────────
_DAILY_AGGREGATE_FIELDS = {"steps", "calories_burned", "distance_km", "active_minutes", "floors"}

# ── Metrics that are point-in-time (latest reading wins) ─────────────────────
_POINT_IN_TIME_FIELDS = {"heart_rate", "spo2", "temperature", "weight"}


def compute_sleep_score(
    duration_min: int | None,
    light_min: int | None = None,
    deep_min: int | None = None,
    rem_min: int | None = None,
    awake_min: int | None = None,
) -> int | None:
    """Compute a clinically-grounded sleep score on a 0-100 scale.

    Breakdown:
      - Duration (up to 50 pts): Target 7-9 hours (420-540 min).
      - Deep sleep (up to 25 pts): Target 15-20% of sleep.
      - REM sleep (up to 15 pts): Target 20-25% of sleep.
      - Restfulness / Awake (up to 10 pts): Awake time under 10% of bedtime.
    """
    if duration_min is None or duration_min <= 0:
        return None

    # 1. Duration score (max 50)
    # Ideal: 420 - 540 minutes (7 - 9 hours)
    if 420 <= duration_min <= 540:
        duration_score = 50.0
    elif duration_min < 420:
        duration_score = max(0.0, 50.0 * (duration_min / 420.0))
    else:  # > 540 min
        excess = duration_min - 540
        duration_score = max(35.0, 50.0 - (excess / 60.0) * 5.0)

    # 2. Sleep stages score (if available)
    has_stages = any(v is not None and v > 0 for v in (deep_min, rem_min, light_min))
    if not has_stages:
        return int(round(min(100.0, duration_score * 2.0)))

    # Deep sleep score (max 25) — optimal 15-20%
    deep = deep_min or 0
    deep_ratio = deep / duration_min
    if deep_ratio >= 0.15:
        deep_score = 25.0
    else:
        deep_score = 25.0 * (deep_ratio / 0.15)

    # REM sleep score (max 15) — optimal 20-25%
    rem = rem_min or 0
    rem_ratio = rem / duration_min
    if rem_ratio >= 0.20:
        rem_score = 15.0
    else:
        rem_score = 15.0 * (rem_ratio / 0.20)

    # Restfulness score (max 10) — awake percentage (<8% is optimal)
    awake = awake_min or 0
    total_bed_time = duration_min + awake
    awake_ratio = awake / total_bed_time if total_bed_time > 0 else 0
    if awake_ratio <= 0.08:
        rest_score = 10.0
    elif awake_ratio >= 0.25:
        rest_score = 2.0
    else:
        rest_score = 10.0 - ((awake_ratio - 0.08) / 0.17) * 8.0

    total = duration_score + deep_score + rem_score + rest_score
    return int(round(min(100.0, max(0.0, total))))


@router.post("/ingest", response_model=VitalsOut, status_code=201)
def ingest_vitals(
    body: VitalsIngest,
    device: Device = Depends(get_device_from_api_key),
    db: Session = Depends(get_db),
):
    """ESP32 calls this endpoint to push sensor readings."""
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
    user = db.get(User, device.user_id)
    if user is not None and body.weight is not None:
        user.weight = body.weight

    # ── 3. Stamp device last-seen ────────────────────────────────────────
    device.last_seen = now

    db.commit()
    db.refresh(record)
    return record


def _build_latest_vitals(user: User, db: Session) -> VitalsLatestOut:
    """Build the latest vitals snapshot with proper today-only daily metrics."""
    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )

    # Smart on-load auto-sync (if connected and >15 min since last sync)
    token_row = (
        db.query(GoogleHealthToken)
        .filter(GoogleHealthToken.user_id == user.id, GoogleHealthToken.is_active == True)
        .first()
    )
    if token_row:
        last_sync = token_row.last_synced_at
        if last_sync is None or last_sync < now_utc.replace(tzinfo=None) - timedelta(minutes=15):
            try:
                from app.services.google_health_service import sync_google_health
                sync_google_health(user_id=user.id, db=db, hours_back=24)
                db.refresh(token_row)
            except Exception:
                pass  # non-blocking fallback

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
            if val is not None and val > 0:
                if best is None or val > best:
                    best = val
        if best is not None:
            setattr(out, field, best)

    # ── Sleep Session & Sleep Score ──────────────────────────────────────
    latest_sleep = (
        db.query(SleepSession)
        .filter(SleepSession.user_id == user.id)
        .order_by(SleepSession.sleep_date.desc(), SleepSession.id.desc())
        .first()
    )
    if latest_sleep and latest_sleep.duration_min:
        out.sleep_duration_min = latest_sleep.duration_min
        out.sleep_date = latest_sleep.sleep_date
        out.sleep_score = compute_sleep_score(
            latest_sleep.duration_min,
            latest_sleep.light_min,
            latest_sleep.deep_min,
            latest_sleep.rem_min,
            latest_sleep.awake_min,
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
    """Return vitals and sleep history grouped by calendar date."""
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

    sleep_records = (
        db.query(SleepSession)
        .filter(
            SleepSession.user_id == current_user.id,
            SleepSession.sleep_date >= since.date(),
        )
        .order_by(SleepSession.sleep_date.asc())
        .all()
    )
    sleep_by_date: dict[date, SleepSession] = {s.sleep_date: s for s in sleep_records}

    # Group vitals records by calendar date
    by_date: dict[date, list[Vitals]] = {}
    for rec in records:
        d = rec.recorded_at.date()
        by_date.setdefault(d, []).append(rec)

    all_dates = set(by_date.keys()) | set(sleep_by_date.keys())
    summaries = []

    for d in sorted(all_dates):
        recs = by_date.get(d, [])

        # Daily aggregates: take the MAX non-zero value across all sources
        steps = max((r.steps or 0 for r in recs), default=0) or None
        cals = max((r.calories_burned or 0.0 for r in recs), default=0.0) or None
        dist = max((r.distance_km or 0.0 for r in recs), default=0.0) or None
        active = max((r.active_minutes or 0 for r in recs), default=0) or None
        floors = max((r.floors or 0 for r in recs), default=0) or None

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

        sleep_rec = sleep_by_date.get(d)
        sleep_dur = sleep_rec.duration_min if sleep_rec else None
        sleep_sc = (
            compute_sleep_score(
                sleep_rec.duration_min,
                sleep_rec.light_min,
                sleep_rec.deep_min,
                sleep_rec.rem_min,
                sleep_rec.awake_min,
            )
            if sleep_rec
            else None
        )

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
            floors=floors,
            sleep_duration_min=sleep_dur,
            sleep_score=sleep_sc,
            light_min=sleep_rec.light_min if sleep_rec else None,
            deep_min=sleep_rec.deep_min if sleep_rec else None,
            rem_min=sleep_rec.rem_min if sleep_rec else None,
            awake_min=sleep_rec.awake_min if sleep_rec else None,
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
