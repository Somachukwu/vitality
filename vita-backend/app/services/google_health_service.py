"""Google Health API v4 synchronization service.

This module is the only VITALITY component that retrieves cloud health data.
It uses the Google Health v4 REST API directly and deliberately excludes weight:
the smart scale remains the authoritative source for weight readings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.config import settings
from app.core.encryption import decrypt, encrypt
from app.models.google_health_token import GoogleHealthToken
from app.models.sleep_session import SleepSession
from app.models.vitals import Vitals

logger = logging.getLogger(__name__)

_HEALTH_BASE = "https://health.googleapis.com/v4/users/me"
_SOURCE = "google_health"


def _get_credentials(token_row: GoogleHealthToken) -> Credentials | None:
    """Build credentials from VITALITY's encrypted stored OAuth tokens."""
    try:
        access_token = decrypt(token_row.access_token)
        refresh_token = decrypt(token_row.refresh_token) if token_row.refresh_token else None
    except Exception:
        logger.exception("Unable to decrypt Google Health token for user_id=%s", token_row.user_id)
        return None

    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=token_row.scopes or [],
    )
    if token_row.token_expiry:
        credentials.expiry = token_row.token_expiry.replace(tzinfo=None)
    return credentials


def _refresh_if_needed(credentials: Credentials, token_row: GoogleHealthToken, db: Session) -> bool:
    """Refresh an expired token and persist the rotated access token."""
    if credentials.valid:
        return True
    if not credentials.refresh_token:
        token_row.is_active = False
        db.commit()
        return False

    try:
        credentials.refresh(GoogleRequest())
    except Exception as exc:
        logger.warning("Google Health token refresh failed for user_id=%s: %s", token_row.user_id, exc)
        token_row.is_active = False
        db.commit()
        return False

    token_row.access_token = encrypt(credentials.token)
    if credentials.expiry:
        token_row.token_expiry = credentials.expiry.replace(tzinfo=None) if credentials.expiry.tzinfo is None else credentials.expiry.astimezone(timezone.utc).replace(tzinfo=None)
    db.commit()
    return True


def _civil_datetime(value: datetime) -> dict[str, dict[str, int]]:
    value = value.astimezone(timezone.utc)
    return {
        "date": {"year": value.year, "month": value.month, "day": value.day},
        "time": {"hours": value.hour, "minutes": value.minute, "seconds": value.second, "nanos": 0},
    }


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_value(data_points: list[dict[str, Any]], data_key: str, value_key: str) -> float | None:
    for point in reversed(data_points):
        value = _as_number(point.get(data_key, {}).get(value_key))
        if value is not None:
            return value
    return None


def _get_json(url: str, headers: dict[str, str], **kwargs: Any) -> dict[str, Any]:
    response = requests.get(url, headers=headers, timeout=20, **kwargs)
    response.raise_for_status()
    return response.json()


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def _daily_rollup(headers: dict[str, str], data_type: str, start: datetime, end: datetime) -> dict[str, Any] | None:
    """Return the single daily rollup value for a supported Google Health type."""
    url = f"{_HEALTH_BASE}/dataTypes/{data_type}/dataPoints:dailyRollUp"
    payload = {
        "range": {"start": _civil_datetime(start), "end": _civil_datetime(end)},
        "windowSizeDays": 1,
        "pageSize": 1,
    }
    try:
        result = _post_json(url, headers, payload)
        points = result.get("rollupDataPoints", [])
        return points[0] if points else None
    except requests.RequestException as exc:
        logger.info("Google Health %s rollup unavailable: %s", data_type, exc)
        return None


def _list_data_points(headers: dict[str, str], data_type: str, filter_expression: str = "", page_size: int = 50, max_pages: int = 1) -> list[dict[str, Any]]:
    """List matching data points and follow any pagination token up to max_pages."""
    url = f"{_HEALTH_BASE}/dataTypes/{data_type}/dataPoints"
    params: dict[str, Any] = {"pageSize": page_size}
    if filter_expression:
        params["filter"] = filter_expression
    points: list[dict[str, Any]] = []
    pages = 0
    try:
        while pages < max_pages:
            result = _get_json(url, headers, params=params)
            pts = result.get("dataPoints", [])
            points.extend(pts)
            token = result.get("nextPageToken")
            if not token or not pts:
                break
            params["pageToken"] = token
            pages += 1
    except requests.RequestException as exc:
        logger.info("Google Health %s query unavailable: %s", data_type, exc)
    return points


def _fetch_daily_metrics(headers: dict[str, str], start: datetime, end: datetime) -> dict[str, float | int]:
    """Retrieve VITALITY's daily aggregate fields concurrently through v4 dailyRollUp."""
    from concurrent.futures import ThreadPoolExecutor
    metrics: dict[str, float | int] = {}
    dtypes = ["steps", "total-calories", "distance", "active-minutes", "floors"]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {dtype: executor.submit(_daily_rollup, headers, dtype, start, end) for dtype in dtypes}
        rollups = {dtype: f.result() for dtype, f in futures.items()}

    count = _as_number((rollups["steps"] or {}).get("steps", {}).get("countSum"))
    if count is not None:
        metrics["steps"] = int(count)
    kcal = _as_number((rollups["calories"] or {}).get("totalCalories", {}).get("kcalSum"))
    if kcal is not None:
        metrics["calories_burned"] = round(kcal, 1)
    millimeters = _as_number((rollups["distance"] or {}).get("distance", {}).get("millimetersSum"))
    if millimeters is not None:
        metrics["distance_km"] = round(millimeters / 1_000_000, 2)
    active_values = (rollups["active"] or {}).get("activeMinutes", {}).get("activeMinutesRollupByActivityLevel", [])
    if active_values:
        metrics["active_minutes"] = int(sum(_as_number(item.get("activeMinutesSum")) or 0 for item in active_values))
    floors = _as_number((rollups["floors"] or {}).get("floors", {}).get("countSum"))
    if floors is not None:
        metrics["floors"] = int(floors)
    return metrics


def _fetch_latest_metrics(headers: dict[str, str], start: datetime, end: datetime) -> dict[str, float]:
    """Retrieve VITALITY's point-in-time fields concurrently through the v4 list endpoint."""
    from concurrent.futures import ThreadPoolExecutor
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics: dict[str, float] = {}

    def _get_hr():
        hr_points = _list_data_points(headers, "heart-rate", f'heart_rate.sample_time.physical_time >= "{start_iso}" AND heart_rate.sample_time.physical_time < "{end_iso}"', page_size=20, max_pages=1)
        if not hr_points:
            hr_points = _list_data_points(headers, "heart-rate", "", page_size=20, max_pages=1)
        hr_val = _latest_value(hr_points, "heartRate", "beatsPerMinute")
        if hr_val is None:
            rhr_points = _list_data_points(headers, "daily-resting-heart-rate", "", page_size=10, max_pages=1)
            hr_val = _latest_value(rhr_points, "dailyRestingHeartRate", "beatsPerMinute") or _latest_value(rhr_points, "restingHeartRate", "beatsPerMinute")
        return hr_val

    def _get_spo2():
        spo2_points = _list_data_points(headers, "oxygen-saturation", f'oxygen_saturation.sample_time.physical_time >= "{start_iso}" AND oxygen_saturation.sample_time.physical_time < "{end_iso}"', page_size=20, max_pages=1)
        if not spo2_points:
            spo2_points = _list_data_points(headers, "oxygen-saturation", "", page_size=20, max_pages=1)
        spo2_val = _latest_value(spo2_points, "oxygenSaturation", "percentage")
        if spo2_val is None:
            d_spo2_points = _list_data_points(headers, "daily-oxygen-saturation", "", page_size=10, max_pages=1)
            for point in reversed(d_spo2_points):
                daily_data = point.get("dailyOxygenSaturation", {})
                val = _as_number(daily_data.get("averagePercentage") or daily_data.get("percentage") or daily_data.get("lowerBoundPercentage"))
                if val is not None:
                    spo2_val = val
                    break
        return spo2_val

    def _get_temp():
        temp_points = _list_data_points(headers, "core-body-temperature", "", page_size=10, max_pages=1)
        return _latest_value(temp_points, "coreBodyTemperature", "temperatureCelsius")

    with ThreadPoolExecutor(max_workers=3) as executor:
        f_hr = executor.submit(_get_hr)
        f_spo2 = executor.submit(_get_spo2)
        f_temp = executor.submit(_get_temp)

        hr_res = f_hr.result()
        spo2_res = f_spo2.result()
        temp_res = f_temp.result()

    if hr_res is not None:
        metrics["heart_rate"] = round(hr_res, 1)
    if spo2_res is not None:
        metrics["spo2"] = round(spo2_res, 1)
    if temp_res is not None:
        metrics["temperature"] = round(temp_res, 1)

    return metrics


def _parse_google_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _sync_sleep_sessions(user_id: int, db: Session, headers: dict[str, str], start: datetime, end: datetime) -> int:
    start_iso = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    filter_expr = f'sleep.interval.end_time >= "{start_iso}" AND sleep.interval.end_time < "{end_iso}"'
    points = _list_data_points(headers, "sleep", filter_expr, page_size=25)
    if not points:
        points = _list_data_points(headers, "sleep", "", page_size=25)
    created = 0
    for point in points:
        sleep = point.get("sleep", {})
        interval = sleep.get("interval", {})
        sleep_start = _parse_google_datetime(interval.get("startTime"))
        sleep_end = _parse_google_datetime(interval.get("endTime"))
        if not sleep_start or not sleep_end or sleep_end <= sleep_start:
            continue
        summary = sleep.get("summary", {})
        duration = _as_number(summary.get("minutesInSleepPeriod") or summary.get("duration") or sleep.get("duration"))
        duration_min = int(duration) if duration is not None else int((sleep_end - sleep_start).total_seconds() // 60)

        # Extract sleep stages (try stagesSummary first, then individual stages list)
        stages: dict[str, int] = {}
        for stage in (summary.get("stagesSummary") or sleep.get("stagesSummary") or []):
            st_type = stage.get("type")
            mins = _as_number(stage.get("minutes"))
            if st_type and mins is not None:
                stages[st_type] = int(mins)

        if not stages:
            for stage in (sleep.get("stages") or summary.get("stages") or []):
                st_type = stage.get("type")
                if not st_type:
                    continue
                s_st = _parse_google_datetime(stage.get("startTime"))
                s_et = _parse_google_datetime(stage.get("endTime"))
                if s_st and s_et and s_et > s_st:
                    mins = int((s_et - s_st).total_seconds() // 60)
                    stages[st_type] = stages.get(st_type, 0) + mins

        # Attribute sleep date to the morning you wake up (sleep_end), or fallback to start
        sleep_session_date = (sleep_end or sleep_start).date()

        existing = db.query(SleepSession).filter(
            SleepSession.user_id == user_id,
            SleepSession.sleep_date == sleep_session_date,
            SleepSession.source == _SOURCE,
        ).first()
        if not existing:
            existing = SleepSession(user_id=user_id, sleep_date=sleep_session_date, source=_SOURCE)
            db.add(existing)
            created += 1
        existing.sleep_start = sleep_start
        existing.sleep_end = sleep_end
        existing.duration_min = duration_min
        existing.light_min = stages.get("LIGHT")
        existing.deep_min = stages.get("DEEP")
        existing.rem_min = stages.get("REM")
        existing.awake_min = stages.get("AWAKE")
    return created


def sync_google_health(user_id: int, db: Session, hours_back: int = 72) -> dict[str, int]:
    """Synchronize Google Health v4 data into VITALITY's Vitals and SleepSession records."""
    from concurrent.futures import ThreadPoolExecutor
    token_row = db.query(GoogleHealthToken).filter(
        GoogleHealthToken.user_id == user_id,
        GoogleHealthToken.is_active.is_(True),
    ).first()
    if not token_row:
        return {"synced_count": 0, "sleep_sessions_synced": 0}
    credentials = _get_credentials(token_row)
    if not credentials or not _refresh_if_needed(credentials, token_row, db):
        return {"synced_count": 0, "sleep_sessions_synced": 0}

    now = datetime.now(timezone.utc)
    sync_start = now - timedelta(hours=hours_back)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    headers = {"Authorization": f"Bearer {credentials.token}", "Accept": "application/json"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_daily = executor.submit(_fetch_daily_metrics, headers, today_start, today_start + timedelta(days=1))
        f_latest = executor.submit(_fetch_latest_metrics, headers, sync_start, now)

        metrics = f_daily.result()
        metrics.update(f_latest.result())
    synced_count = 0
    if metrics:
        record = db.query(Vitals).filter(
            Vitals.user_id == user_id,
            Vitals.source == _SOURCE,
            Vitals.recorded_at >= today_start.replace(tzinfo=None),
        ).first()
        if not record:
            record = Vitals(user_id=user_id, device_id=None, source=_SOURCE, recorded_at=now.replace(tzinfo=None))
            db.add(record)
        for field, value in metrics.items():
            setattr(record, field, value)
        record.recorded_at = now.replace(tzinfo=None)
        synced_count = len(metrics)

    sleep_sessions_synced = _sync_sleep_sessions(user_id, db, headers, sync_start, now)
    token_row.last_synced_at = now.replace(tzinfo=None)
    db.commit()
    logger.info("Google Health sync complete: user_id=%s vitals=%s sleep_sessions=%s", user_id, synced_count, sleep_sessions_synced)
    return {"synced_count": synced_count, "sleep_sessions_synced": sleep_sessions_synced}
