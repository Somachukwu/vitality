from collections import deque
from datetime import datetime, timedelta, timezone, date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_device_from_api_key
from app.database import SessionLocal, get_db
from app.models.device import Device
from app.models.user import User
from app.models.vitals import Vitals
from app.models.sleep_session import SleepSession
from app.models.google_health_token import GoogleHealthToken
from app.schemas.vitals import (
    VitalsIngest, VitalsLatestOut, VitalsOut,
    VitalsDailySummary, VitalsContinuousPoint, SyncAllOut,
    ScaleLiveResponse, ScaleLogWeightIn, ScaleReadingPoint,
)

router = APIRouter(prefix="/vitals", tags=["vitals"])

# Transient in-memory buffer for continuous smart scale readings (user_id -> deque of readings)
_live_scale_readings: dict[int, deque] = {}


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
    """ESP32 calls this endpoint to push sensor readings or send periodic heartbeat pings."""
    now = datetime.now(timezone.utc)
    device.last_seen = now

    has_wearable_data = (
        body.heart_rate is not None
        or body.spo2 is not None
        or body.temperature is not None
        or body.steps is not None
    )
    has_weight_data = body.weight is not None and body.weight > 0

    # ── Continuous Scale Buffer ──────────────────────────────────────────
    # Buffer incoming weight readings into transient live memory for the user.
    # We do NOT immediately write these to the vitals table or update user.weight
    # so arbitrary weigh-ins (pets, other people, packages) do not saturate the DB
    # or corrupt the recommendation engine.
    if has_weight_data:
        weight_val = round(float(body.weight), 2)
        reading_time = body.recorded_at or now
        if device.user_id not in _live_scale_readings:
            _live_scale_readings[device.user_id] = deque(maxlen=30)
        _live_scale_readings[device.user_id].appendleft(
            ScaleReadingPoint(
                weight=weight_val,
                device_id=device.id,
                device_name=device.device_name,
                recorded_at=reading_time,
                received_at=now,
            )
        )

    if has_wearable_data:
        # Wearable data IS inserted into vitals history
        record = Vitals(
            user_id=device.user_id,
            device_id=device.id,
            heart_rate=body.heart_rate,
            spo2=body.spo2,
            temperature=body.temperature,
            steps=body.steps,
            recorded_at=body.recorded_at or now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    db.commit()
    # If device only sent weight or heartbeat ping, return 201 Created with valid VitalsOut
    latest_record = (
        db.query(Vitals)
        .filter(Vitals.user_id == device.user_id)
        .order_by(Vitals.recorded_at.desc())
        .first()
    )
    if latest_record:
        if has_weight_data:
            out = VitalsOut.model_validate(latest_record)
            out.weight = round(float(body.weight), 2)
            return out
        return latest_record

    return VitalsOut(
        id=0,
        heart_rate=None,
        spo2=None,
        temperature=None,
        weight=round(float(body.weight), 2) if has_weight_data else None,
        steps=None,
        source="station",
        recorded_at=now,
    )



def _auto_sync_if_needed(user_id: int, db: Session, minutes: int = 15) -> Optional[GoogleHealthToken]:
    """Trigger Google Health sync if user has an active token and >15 min since last sync."""
    token_row = (
        db.query(GoogleHealthToken)
        .filter(GoogleHealthToken.user_id == user_id, GoogleHealthToken.is_active == True)
        .first()
    )
    if token_row:
        now_utc = datetime.now(timezone.utc)
        last_sync = token_row.last_synced_at
        if last_sync is None or last_sync < now_utc.replace(tzinfo=None) - timedelta(minutes=minutes):
            try:
                from app.services.google_health_service import sync_google_health
                sync_google_health(user_id=user_id, db=db, hours_back=72)
                db.refresh(token_row)
            except Exception:
                pass  # non-blocking fallback
    return token_row


def _build_latest_vitals(user: User, db: Session, target_date_str: Optional[str] = None) -> VitalsLatestOut:
    """Build the latest vitals snapshot with proper today-only daily metrics."""
    if target_date_str:
        try:
            parsed_date = datetime.strptime(target_date_str.strip()[:10], "%Y-%m-%d").date()
            today_start = datetime.combine(parsed_date, datetime.min.time())
        except ValueError:
            now_utc = datetime.now(timezone.utc)
            today_start = now_utc.replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=None
            )
    else:
        now_utc = datetime.now(timezone.utc)
        today_start = now_utc.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

    today_end = today_start + timedelta(days=1)

    # Smart on-load auto-sync (if connected and >15 min since last sync)
    token_row = _auto_sync_if_needed(user.id, db)

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

    # ── Daily aggregates: TODAY only (reset at 12:00 AM) ────────────────
    for field in _DAILY_AGGREGATE_FIELDS:
        setattr(out, field, None)

    today_records = (
        db.query(Vitals)
        .filter(
            Vitals.user_id == user.id,
            Vitals.recorded_at >= today_start,
            Vitals.recorded_at < today_end,
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
    date_str: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_latest_vitals(current_user, db, target_date_str=date_str)


@router.get("/history", response_model=list[VitalsDailySummary])
def get_vitals_history(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return vitals and sleep history grouped by calendar date."""
    _auto_sync_if_needed(current_user.id, db)

    days = max(1, days)
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start_date, datetime.min.time())

    records = (
        db.query(Vitals)
        .filter(
            Vitals.user_id == current_user.id,
            Vitals.recorded_at >= start_dt,
        )
        .order_by(Vitals.recorded_at.asc())
        .all()
    )

    sleep_records = (
        db.query(SleepSession)
        .filter(
            SleepSession.user_id == current_user.id,
            SleepSession.sleep_date >= start_date,
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

    calendar_dates = [start_date + timedelta(days=i) for i in range(days)]
    all_dates = sorted(
        set(calendar_dates)
        | {d for d in by_date.keys() if d >= start_date}
        | {d for d in sleep_by_date.keys() if d >= start_date}
    )
    summaries = []

    for d in all_dates:
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


@router.get("/continuous", response_model=list[VitalsContinuousPoint])
def get_vitals_continuous(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return individual timestamped HR / SpO₂ readings for continuous charting.

    Unlike /history which groups by day, this endpoint returns every recorded
    data point so the frontend can plot high-resolution time-series charts.
    """
    # Auto-sync Google Health in background if connected and stale
    _auto_sync_if_needed(current_user.id, db)

    if days <= 1:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    else:
        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=max(1, days) - 1)
        since = datetime.combine(start_date, datetime.min.time())

    records = (
        db.query(
            Vitals.recorded_at,
            Vitals.heart_rate,
            Vitals.spo2,
        )
        .filter(
            Vitals.user_id == current_user.id,
            Vitals.recorded_at >= since,
            # Exclude daily rollup summaries (which have source 'google_health' and artificial timestamps)
            Vitals.source != "google_health",
        )
        # At least one of HR or SpO₂ must be present
        .filter(
            (Vitals.heart_rate.isnot(None)) | (Vitals.spo2.isnot(None))
        )
        .order_by(Vitals.recorded_at.asc())
        .all()
    )

    return [
        VitalsContinuousPoint(
            recorded_at=r.recorded_at.replace(tzinfo=timezone.utc) if r.recorded_at.tzinfo is None else r.recorded_at,
            heart_rate=r.heart_rate,
            spo2=r.spo2,
        )
        for r in records
    ]


def _run_recommendation_background(user_id: int):
    """Evaluate recommendation engine in background after sync."""
    from recommendation_engine.recommendation_service import generate_and_persist_recommendations
    bg_db = SessionLocal()
    try:
        generate_and_persist_recommendations(user_id, bg_db)
    except Exception:
        pass
    finally:
        bg_db.close()


@router.post("/sync-all", response_model=SyncAllOut)
def sync_all(
    background_tasks: BackgroundTasks,
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
            user_id=current_user.id, db=db, hours_back=72
        )
        google_synced = True
        synced_count = result["synced_count"]
        sleep_sessions_synced = result["sleep_sessions_synced"]
        background_tasks.add_task(_run_recommendation_background, current_user.id)

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


# ── Smart Scale Endpoints ──────────────────────────────────────────

@router.get("/scale/live", response_model=ScaleLiveResponse)
def get_scale_live_readings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return continuous readings streamed from the smart scale, device status, and official weight."""
    station_dev = (
        db.query(Device)
        .filter(Device.user_id == current_user.id, Device.device_type == "station")
        .order_by(Device.last_seen.desc().nullslast())
        .first()
    )

    now_utc = datetime.now(timezone.utc)
    is_online = False
    last_seen = None
    device_name = None

    if station_dev:
        device_name = station_dev.device_name
        last_seen = station_dev.last_seen
        if last_seen:
            # Device is considered online if seen within 2.5 minutes (heartbeat is 30s)
            diff = now_utc.replace(tzinfo=None) - last_seen.replace(tzinfo=None)
            if diff.total_seconds() < 150:
                is_online = True

    readings_deque = _live_scale_readings.get(current_user.id)
    recent_readings = list(readings_deque) if readings_deque else []
    latest_reading = recent_readings[0] if recent_readings else None

    # Get official profile weight
    current_weight = current_user.weight
    if current_weight is None:
        latest_vital = (
            db.query(Vitals)
            .filter(Vitals.user_id == current_user.id, Vitals.weight.isnot(None))
            .order_by(Vitals.recorded_at.desc())
            .first()
        )
        if latest_vital:
            current_weight = latest_vital.weight

    return ScaleLiveResponse(
        device_registered=station_dev is not None,
        device_name=device_name,
        is_online=is_online,
        last_seen=last_seen,
        current_logged_weight=round(float(current_weight), 2) if current_weight is not None else None,
        latest_reading=latest_reading,
        recent_readings=recent_readings,
    )


@router.post("/scale/log", response_model=VitalsOut, status_code=201)
def log_scale_weight(
    body: ScaleLogWeightIn,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Commit a selected weight reading to the database and update user profile & recommendations."""
    if body.weight <= 0 or body.weight > 400:
        raise HTTPException(status_code=400, detail="Invalid weight reading (must be 1–400 kg)")

    now = datetime.now(timezone.utc)
    rec_time = body.recorded_at or now

    station_dev = (
        db.query(Device)
        .filter(Device.user_id == current_user.id, Device.device_type == "station")
        .first()
    )

    weight_val = round(float(body.weight), 2)

    # 1. Persist official Vitals record
    record = Vitals(
        user_id=current_user.id,
        device_id=station_dev.id if station_dev else None,
        weight=weight_val,
        source="station",
        recorded_at=rec_time,
    )
    db.add(record)

    # 2. Update user profile weight
    user = db.get(User, current_user.id)
    if user:
        user.weight = weight_val

    db.commit()
    db.refresh(record)

    # 3. Trigger recommendation engine update in background
    background_tasks.add_task(_run_recommendation_background, current_user.id)

    return record


@router.post("/scale/simulate", response_model=ScaleReadingPoint)
def simulate_scale_reading(
    body: ScaleLogWeightIn,
    current_user: User = Depends(get_current_user),
):
    """Simulate an incoming live weight reading from the scale (for testing / development)."""
    if body.weight <= 0 or body.weight > 400:
        raise HTTPException(status_code=400, detail="Invalid weight reading (must be 1–400 kg)")

    now = datetime.now(timezone.utc)
    weight_val = round(float(body.weight), 2)
    reading = ScaleReadingPoint(
        weight=weight_val,
        device_id=None,
        device_name="Simulated Scale",
        recorded_at=body.recorded_at or now,
        received_at=now,
    )
    if current_user.id not in _live_scale_readings:
        _live_scale_readings[current_user.id] = deque(maxlen=30)
    _live_scale_readings[current_user.id].appendleft(reading)
    return reading

