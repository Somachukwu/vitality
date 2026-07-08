from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_device_from_api_key
from app.database import get_db
from app.models.device import Device
from app.models.user import User
from app.models.vitals import Vitals
from app.schemas.vitals import VitalsIngest, VitalsLatestOut, VitalsOut

router = APIRouter(prefix="/vitals", tags=["vitals"])


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


@router.get("/latest", response_model=VitalsLatestOut)
def get_latest_vitals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(Vitals)
        .filter(Vitals.user_id == current_user.id)
        .order_by(Vitals.recorded_at.desc())
        .first()
    )
    if record is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No vitals recorded yet")

    out = VitalsLatestOut.model_validate(record)
    if record.device:
        out.device_name = record.device.device_name
    return out


@router.get("/history", response_model=list[VitalsOut])
def get_vitals_history(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    records = (
        db.query(Vitals)
        .filter(Vitals.user_id == current_user.id, Vitals.recorded_at >= since)
        .order_by(Vitals.recorded_at.asc())
        .all()
    )
    return records
