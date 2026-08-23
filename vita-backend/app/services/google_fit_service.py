"""
Google Health API + Google Fit REST API sync service.

THIS IS THE ONLY FILE that talks to Google's health/fitness APIs.
If Google deprecates either API, only this file requires changes — the
router and models stay the same.

Weight is intentionally excluded from all syncs — it comes from the
smart scale hardware only and must not be overwritten by Google Fit data.

PERFORMANCE: Google Health API v4 requests are made in parallel using
httpx.AsyncClient (run via asyncio.run from the sync caller). This
reduces sync time from ~15-25s to ~2-4s.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.core.encryption import decrypt, encrypt
from app.models.google_health_token import GoogleHealthToken
from app.models.sleep_session import SleepSession
from app.models.vitals import Vitals

logger = logging.getLogger(__name__)

_FIT_BASE = "https://www.googleapis.com/fitness/v1/users/me"
_HEALTH_BASE = "https://health.googleapis.com/v4/users/me"

# Sleep stage codes from the Google Fit API
SLEEP_STAGE_LIGHT  = 4
SLEEP_STAGE_DEEP   = 5
SLEEP_STAGE_REM    = 6
SLEEP_STAGE_AWAKE  = 1


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_number(val) -> float | int | None:
    """Helper to extract a numeric metric value from Google Health API union objects."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, dict):
        for k in ("count", "kilocalories", "calories", "meters", "bpm",
                   "percentage", "degreesCelsius", "degrees_celsius",
                   "minutes", "value", "fpVal", "intVal"):
            if k in val:
                return _extract_number(val[k])
        for v in val.values():
            res = _extract_number(v)
            if res is not None:
                return res
    return None


def _ns_to_utc(ns: str | int) -> datetime:
    """Convert Google Fit nanosecond timestamp to UTC datetime."""
    return datetime.fromtimestamp(int(ns) / 1e9, tz=timezone.utc).replace(tzinfo=None)


# ── Credential management ───────────────────────────────────────────────────

def _get_credentials(token_row: GoogleHealthToken) -> Credentials | None:
    """
    Build a google.oauth2.credentials.Credentials object from the stored token row.
    Automatically refreshes if the access token is expired.
    Returns None if the token is permanently invalid.
    """
    from app.config import settings

    try:
        access_token  = decrypt(token_row.access_token)
        refresh_token = decrypt(token_row.refresh_token) if token_row.refresh_token else None
    except Exception:
        logger.error("Failed to decrypt tokens for user_id=%s", token_row.user_id)
        return None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=token_row.scopes or [],
    )

    if token_row.token_expiry:
        creds.expiry = token_row.token_expiry

    return creds


def _refresh_if_needed(creds: Credentials, token_row: GoogleHealthToken, db: Session) -> bool:
    """
    Refresh the access token if it has expired or is about to expire.
    Updates the token row in DB with the new encrypted access token + expiry.
    Returns True if credentials are valid, False if refresh failed.
    """
    if creds.valid:
        return True

    try:
        creds.refresh(GoogleRequest())
    except Exception as exc:
        logger.warning("Token refresh failed for user_id=%s: %s", token_row.user_id, exc)
        token_row.is_active = False
        db.commit()
        return False

    token_row.access_token = encrypt(creds.token)
    if creds.expiry:
        token_row.token_expiry = creds.expiry.replace(tzinfo=None)
    db.commit()
    return True


# ── Google Health API v4 (parallel) ──────────────────────────────────────────

# Mapping: internal key → (Google Health API data type slug, aggregation mode)
_HEALTH_TYPE_MAP = {
    "steps":           ("steps",              "sum"),
    "calories_burned": ("calories-burned",    "sum"),
    "distance_km":     ("distance",           "sum_dist"),
    "active_minutes":  ("active-minutes",     "sum"),
    "heart_rate":      ("heart-rate",         "latest"),
    "spo2":            ("oxygen-saturation",  "latest"),
    "temperature":     ("body-temperature",   "latest"),
}


async def _fetch_health_metric(
    client: httpx.AsyncClient,
    headers: dict,
    metric_key: str,
    data_type: str,
    agg_mode: str,
    start_iso: str,
    end_iso: str,
) -> tuple[str, float | int | None]:
    """Fetch a single metric from Google Health API v4. Returns (key, value)."""
    for suffix in (
        f"dataTypes/{data_type}/dataPoints:reconcile",
        f"dataTypes/{data_type}/dataPoints",
    ):
        url = f"{_HEALTH_BASE}/{suffix}?startTime={start_iso}&endTime={end_iso}"
        try:
            resp = await client.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            pts = data.get("dataPoints", []) or data.get("points", []) or []
            if not pts:
                continue

            extracted = [v for p in pts if (v := _extract_number(p)) is not None]
            if not extracted:
                continue

            if agg_mode == "sum":
                total = sum(extracted)
                if total > 0:
                    return metric_key, (int(total) if metric_key == "steps" else round(float(total), 1))
            elif agg_mode == "sum_dist":
                total = sum(extracted)
                if total > 0:
                    # Google returns meters if value > 50, km otherwise
                    return metric_key, round(float(total) / 1000.0 if total > 50 else float(total), 2)
            elif agg_mode == "latest":
                val = extracted[-1]
                if val > 0:
                    return metric_key, round(float(val), 1)
            return metric_key, None
        except Exception as e:
            logger.debug("Google Health API fetch error for %s: %s", data_type, e)

    return metric_key, None


async def _fetch_all_health_metrics(token: str, start_dt: datetime, end_dt: datetime) -> dict[str, float | int]:
    """Fetch ALL Google Health API v4 metrics in parallel (~2s instead of ~15s)."""
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso   = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    headers   = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_health_metric(client, headers, key, dt, agg, start_iso, end_iso)
            for key, (dt, agg) in _HEALTH_TYPE_MAP.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    metrics: dict[str, float | int] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.debug("Health API parallel fetch error: %s", r)
            continue
        key, val = r
        if val is not None:
            metrics[key] = val

    return metrics


# ── Google Fit REST API (legacy) ─────────────────────────────────────────────

def _fetch_aggregate(creds: Credentials, start_dt: datetime, end_dt: datetime) -> dict | None:
    """Query Google Fit dataset:aggregate endpoint for daily summary metrics."""
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    url = f"{_FIT_BASE}/dataset:aggregate"
    headers = {"Authorization": f"Bearer {creds.token}"}
    body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.distance.delta"},
            {"dataTypeName": "com.google.active_minutes"},
            {"dataTypeName": "com.google.heart_rate.bpm"},
            {"dataTypeName": "com.google.oxygen_saturation"},
            {"dataTypeName": "com.google.body.temperature"},
        ],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": start_ms,
        "endTimeMillis": end_ms,
    }

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Google Fit aggregate query returned status %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Google Fit aggregate query failed: %s", exc)

    return None


def _fetch_from_datasources(creds: Credentials, start_dt: datetime, end_dt: datetime) -> dict[str, float | int]:
    """
    Fetch raw/derived data points directly from all active user data sources.
    Handles device-specific streams (like Xiaomi, Fitbit, Health Connect).
    """
    start_ns = int(start_dt.timestamp() * 1e9)
    end_ns   = int(end_dt.timestamp() * 1e9)
    headers  = {"Authorization": f"Bearer {creds.token}"}
    metrics: dict[str, float | int] = {}

    try:
        ds_resp = requests.get(f"{_FIT_BASE}/dataSources", headers=headers, timeout=15)
        if ds_resp.status_code != 200:
            return metrics

        sources = ds_resp.json().get("dataSource", [])
        for s in sources:
            ds_id   = s.get("dataStreamId")
            ds_type = s.get("dataType", {}).get("name", "")
            if not ds_id:
                continue

            try:
                ds_url = f"{_FIT_BASE}/dataSources/{ds_id}/datasets/{start_ns}-{end_ns}"
                r = requests.get(ds_url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                pts = r.json().get("point", [])
                if not pts:
                    continue

                if "step_count" in ds_type or "step_count" in ds_id:
                    if "cumulative" in ds_type or "cumulative" in ds_id:
                        max_steps = max((p.get("value", [{}])[0].get("intVal", 0) for p in pts), default=0)
                        if max_steps > 0:
                            metrics["steps"] = max(int(metrics.get("steps", 0)), max_steps)
                    else:
                        sum_steps = sum(p.get("value", [{}])[0].get("intVal", 0) for p in pts)
                        if sum_steps > 0:
                            metrics["steps"] = max(int(metrics.get("steps", 0)), sum_steps)
                elif "calories.expended" in ds_type or "calories.expended" in ds_id:
                    sum_cal = sum(p.get("value", [{}])[0].get("fpVal", 0.0) for p in pts)
                    if sum_cal > 0:
                        metrics["calories_burned"] = round(max(float(metrics.get("calories_burned", 0.0)), sum_cal), 1)
                elif "distance" in ds_type or "distance" in ds_id:
                    sum_dist = sum(p.get("value", [{}])[0].get("fpVal", 0.0) for p in pts)
                    if sum_dist > 0:
                        metrics["distance_km"] = round(max(float(metrics.get("distance_km", 0.0)), sum_dist / 1000.0), 2)
                elif "heart_rate" in ds_type or "heart_rate" in ds_id:
                    val = pts[-1].get("value", [{}])[0].get("fpVal")
                    if val:
                        metrics["heart_rate"] = round(val, 1)
                elif "oxygen_saturation" in ds_type or "oxygen_saturation" in ds_id:
                    val = pts[-1].get("value", [{}])[0].get("fpVal")
                    if val:
                        metrics["spo2"] = round(val, 1)
                elif "body.temperature" in ds_type or "body.temperature" in ds_id:
                    val = pts[-1].get("value", [{}])[0].get("fpVal")
                    if val:
                        metrics["temperature"] = round(val, 1)
                elif "active_minutes" in ds_type or "active_minutes" in ds_id:
                    sum_act = sum(p.get("value", [{}])[0].get("intVal", 0) for p in pts)
                    if sum_act > 0:
                        metrics["active_minutes"] = max(int(metrics.get("active_minutes", 0)), sum_act)
            except Exception as e:
                logger.debug("Error reading data source %s: %s", ds_id, e)
    except Exception as exc:
        logger.warning("Error scanning data sources: %s", exc)

    return metrics


# ── Main sync orchestrator ───────────────────────────────────────────────────

def sync_google_fit(user_id: int, db: Session, hours_back: int = 24) -> dict:
    """
    Pull the last `hours_back` hours of Google Fit data for the given user.
    Inserts new Vitals rows and SleepSession rows. Does NOT overwrite weight
    (weight comes from the smart scale hardware only).

    Returns: { "synced_count": int, "sleep_sessions_synced": int }
    """
    token_row = db.query(GoogleHealthToken).filter(
        GoogleHealthToken.user_id == user_id,
        GoogleHealthToken.is_active == True,
    ).first()

    if not token_row:
        return {"synced_count": 0, "sleep_sessions_synced": 0}

    creds = _get_credentials(token_row)
    if not creds:
        return {"synced_count": 0, "sleep_sessions_synced": 0}

    if not _refresh_if_needed(creds, token_row, db):
        return {"synced_count": 0, "sleep_sessions_synced": 0}

    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(hours=hours_back)

    synced_count = 0
    sleep_sessions_synced = 0

    # ── 1. Fetch from Google Health API v4 (PARALLEL — fast) ────────────
    collected_metrics: dict[str, float | int] = {}
    try:
        health_metrics = asyncio.run(
            _fetch_all_health_metrics(creds.token, start_dt, end_dt)
        )
        collected_metrics.update(health_metrics)
        logger.info("Google Health API v4 returned %d metrics", len(health_metrics))
    except Exception as exc:
        logger.warning("Google Health API v4 parallel fetch failed: %s", exc)

    # ── 2. Fetch from Google Fit REST API (legacy fallback) ─────────────
    # Only fill in metrics that Health API didn't provide
    agg_data = _fetch_aggregate(creds, start_dt, end_dt)
    if agg_data and "bucket" in agg_data:
        for bucket in agg_data.get("bucket", []):
            for dataset in bucket.get("dataset", []):
                ds_id = dataset.get("dataSourceId", "")
                points = dataset.get("point", [])
                if not points:
                    continue

                if "step_count" in ds_id:
                    total_steps = sum(p.get("value", [{}])[0].get("intVal", 0) for p in points)
                    if total_steps > 0 and total_steps > collected_metrics.get("steps", 0):
                        collected_metrics["steps"] = total_steps
                elif "calories" in ds_id:
                    total_cal = sum(p.get("value", [{}])[0].get("fpVal", 0.0) for p in points)
                    if total_cal > 0 and "calories_burned" not in collected_metrics:
                        collected_metrics["calories_burned"] = round(total_cal, 1)
                elif "distance" in ds_id:
                    total_dist_m = sum(p.get("value", [{}])[0].get("fpVal", 0.0) for p in points)
                    if total_dist_m > 0 and "distance_km" not in collected_metrics:
                        collected_metrics["distance_km"] = round(total_dist_m / 1000.0, 2)
                elif "active_minutes" in ds_id:
                    total_act = sum(p.get("value", [{}])[0].get("intVal", 0) for p in points)
                    if total_act > 0 and "active_minutes" not in collected_metrics:
                        collected_metrics["active_minutes"] = total_act
                elif "heart_rate" in ds_id:
                    val = points[-1].get("value", [{}])[0].get("fpVal")
                    if val and "heart_rate" not in collected_metrics:
                        collected_metrics["heart_rate"] = round(val, 1)
                elif "oxygen_saturation" in ds_id:
                    val = points[-1].get("value", [{}])[0].get("fpVal")
                    if val and "spo2" not in collected_metrics:
                        collected_metrics["spo2"] = round(val, 1)
                elif "body.temperature" in ds_id:
                    val = points[-1].get("value", [{}])[0].get("fpVal")
                    if val and "temperature" not in collected_metrics:
                        collected_metrics["temperature"] = round(val, 1)

    # Merge in data from active device streams (only if not already present)
    stream_metrics = _fetch_from_datasources(creds, start_dt, end_dt)
    for k, v in stream_metrics.items():
        if k not in collected_metrics or (isinstance(v, (int, float)) and v > collected_metrics.get(k, 0)):
            collected_metrics[k] = v

    if collected_metrics:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        existing = db.query(Vitals).filter(
            Vitals.user_id == user_id,
            Vitals.source == "google_fit",
            Vitals.recorded_at >= today_start,
        ).first()

        if existing:
            for k, v in collected_metrics.items():
                setattr(existing, k, v)
            existing.recorded_at = datetime.now(timezone.utc).replace(tzinfo=None)
            synced_count = 1
        else:
            v_row = Vitals(
                user_id=user_id,
                device_id=None,
                recorded_at=datetime.now(timezone.utc).replace(tzinfo=None),
                source="google_fit",
                **collected_metrics,
            )
            db.add(v_row)
            synced_count = 1

    # ── 3. Sleep Sessions Sync ───────────────────────────────────────────
    try:
        start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        sess_url = f"{_FIT_BASE}/sessions?startTime={start_iso}&endTime={end_iso}&activityType=72"
        sess_resp = requests.get(sess_url, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15)
        if sess_resp.status_code == 200:
            sessions = sess_resp.json().get("session", [])
            for s in sessions:
                s_start_ms = int(s.get("startTimeMillis", 0))
                s_end_ms = int(s.get("endTimeMillis", 0))
                if not s_start_ms or not s_end_ms:
                    continue

                s_start = datetime.fromtimestamp(s_start_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
                s_end = datetime.fromtimestamp(s_end_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
                s_date = s_start.date()
                duration = int((s_end - s_start).total_seconds() / 60)

                existing_s = db.query(SleepSession).filter(
                    SleepSession.user_id == user_id,
                    SleepSession.sleep_date == s_date,
                ).first()

                if existing_s:
                    existing_s.sleep_start = s_start
                    existing_s.sleep_end = s_end
                    existing_s.duration_min = duration
                else:
                    session_row = SleepSession(
                        user_id=user_id,
                        sleep_date=s_date,
                        sleep_start=s_start,
                        sleep_end=s_end,
                        duration_min=duration,
                        source="google_fit",
                    )
                    db.add(session_row)
                    sleep_sessions_synced += 1
    except Exception as exc:
        logger.warning("Failed to fetch sleep sessions: %s", exc)

    # ── 4. Commit & Update Timestamp ─────────────────────────────────────
    token_row.last_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    logger.info(
        "Google Fit sync complete: user_id=%s, vitals=%s, sleep_sessions=%s",
        user_id, synced_count, sleep_sessions_synced,
    )
    return {"synced_count": synced_count, "sleep_sessions_synced": sleep_sessions_synced}
