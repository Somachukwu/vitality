#!/usr/bin/env python3
"""
Vita Diagnostic Tool
====================
Run from vita-backend/:   python diagnose.py

Checks three things in order:
  1. Database — is the ESP32's API key registered and active?
  2. Server   — is the backend reachable at the configured URL?
  3. POST     — does a simulated ESP32 POST succeed end-to-end?

Each section tells you exactly what is wrong and how to fix it.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

SEP = "─" * 62

# ── Read config from adjacent files so this stays in sync automatically ──
def _read_config_value(pattern: str, default: str) -> str:
    cfg = os.path.join(
        os.path.dirname(__file__), "..", "vita-esp32", "vita_wearable", "config.h"
    )
    if os.path.exists(cfg):
        m = re.search(pattern, open(cfg).read())
        if m:
            return m.group(1)
    return default

API_KEY = _read_config_value(
    r'#define\s+DEVICE_API_KEY\s+"([a-f0-9]{64})"',
    "NOT_FOUND_IN_CONFIG",
)

_ingest_url = _read_config_value(
    r'#define\s+SERVER_INGEST_URL\s+"(http://[^"]+)"',
    "http://localhost:8000/api/vitals/ingest",
)
# Derive base URL from ingest URL  (http://ip:port)
SERVER_BASE = "/".join(_ingest_url.split("/")[:3])


# ── Read .env for DB credentials ──────────────────────────────────────────
def _read_env() -> dict:
    cfg = {"host": "localhost", "port": 3306, "user": "root", "password": "", "database": "vita_db"}
    env = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env):
        return cfg
    for line in open(env):
        line = line.strip()
        if   line.startswith("DB_HOST="):     cfg["host"]     = line.split("=", 1)[1]
        elif line.startswith("DB_PORT="):     cfg["port"]     = int(line.split("=", 1)[1])
        elif line.startswith("DB_USER="):     cfg["user"]     = line.split("=", 1)[1]
        elif line.startswith("DB_PASSWORD="): cfg["password"] = line.split("=", 1)[1]
        elif line.startswith("DB_NAME="):     cfg["database"] = line.split("=", 1)[1]
    return cfg


# ── 1. Database check ─────────────────────────────────────────────────────
def check_db() -> None:
    print(f"\n{SEP}")
    print("  1 / 3  —  DATABASE CHECK")
    print(SEP)

    try:
        import pymysql
    except ImportError:
        print("[DB] pymysql not installed — run:  pip install pymysql")
        return

    db_cfg = _read_env()
    try:
        conn = pymysql.connect(connect_timeout=5, **db_cfg)
    except Exception as e:
        print(f"[DB] ✗ Cannot connect to MySQL at {db_cfg['host']}:{db_cfg['port']}: {e}")
        print("[DB]   Is MySQL running?  Check the service / XAMPP / Workbench.")
        return

    print(f"[DB] ✓ Connected to {db_cfg['host']}:{db_cfg['port']}/{db_cfg['database']}")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, device_name, device_type, device_uid, is_active, last_seen, user_id "
            "FROM devices WHERE api_key = %s",
            (API_KEY,),
        )
        row = cur.fetchone()

    if row:
        print(f"[DB] ✓ Device FOUND:")
        print(f"       id        = {row[0]}")
        print(f"       name      = {row[1]}")
        print(f"       type      = {row[2]}")
        print(f"       uid       = {row[3]}")
        print(f"       is_active = {bool(row[4])}")
        print(f"       last_seen = {row[5]}")
        print(f"       user_id   = {row[6]}")
        if not row[4]:
            print()
            print("[DB] ✗ Device is INACTIVE — the ESP32 will receive HTTP 401.")
            print("[DB]   Fix it in MySQL Workbench or run:")
            print(f"[DB]     UPDATE devices SET is_active=1 WHERE id={row[0]};")
    else:
        print(f"[DB] ✗ Device NOT FOUND  (api_key starts with: {API_KEY[:20]}...)")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, device_name, device_type, is_active, api_key FROM devices"
            )
            all_devs = cur.fetchall()

        print(f"\n[DB]   Devices currently in the database: {len(all_devs)}")
        if all_devs:
            for d in all_devs:
                flag = "ACTIVE" if d[3] else "inactive"
                print(f"       id={d[0]}  [{flag}]  {d[1]} ({d[2]})  key={d[4][:20]}...")
        else:
            print("       (none — database is empty)")

        print()
        print("[DB] ✗ ACTION REQUIRED:")
        print("[DB]   The wearable's API key is not registered.")
        print("[DB]   Steps:")
        print("[DB]   1. Flash the wearable once and note the Chip UID on the OLED")
        print("[DB]   2. Log in to the Vita web app")
        print("[DB]   3. Go to Profile > Add Device, enter the Chip UID")
        print("[DB]   4. Copy the returned api_key into vita_wearable/config.h")
        print("[DB]   5. Run find_server_ip.py then reflash")

    conn.close()


# ── 2. Server check ───────────────────────────────────────────────────────
def check_server() -> bool:
    print(f"\n{SEP}")
    print(f"  2 / 3  —  SERVER CHECK  ({SERVER_BASE})")
    print(SEP)
    try:
        resp = urllib.request.urlopen(f"{SERVER_BASE}/api/health", timeout=5)
        data = json.loads(resp.read())
        print(f"[HTTP] ✓ Server is UP: {data}")
        return True
    except urllib.error.URLError as e:
        print(f"[HTTP] ✗ Server is DOWN or unreachable: {e.reason}")
        print()
        print("[HTTP]   Most likely cause: uvicorn is not running, or it was started")
        print("[HTTP]   without  --host 0.0.0.0  (defaults to localhost-only).")
        print()
        print("[HTTP]   Start it correctly:")
        print("[HTTP]     cd vita-backend")
        print("[HTTP]     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        print()
        return False
    except Exception as e:
        print(f"[HTTP] ✗ Unexpected error: {e}")
        return False


# ── 3. Simulated ESP32 POST ───────────────────────────────────────────────
def test_post() -> None:
    print(f"\n{SEP}")
    print("  3 / 3  —  SIMULATED ESP32 POST")
    print(SEP)

    payload = json.dumps({
        "heart_rate": 72.0,
        "spo2": 98.0,
        "temperature": 36.8,
        "steps": 0,
    }).encode()

    req = urllib.request.Request(
        f"{SERVER_BASE}/api/vitals/ingest",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=5)
        body = json.loads(resp.read())
        print(f"[POST] ✓ SUCCESS  (HTTP 201)")
        print(f"[POST]   Saved vitals  id={body.get('id')}")
        print()
        print("[POST] ✓ The backend is fully working end-to-end.")
        print("[POST]   If the ESP32 is still not sending data, the problem is")
        print("[POST]   network-only — not the backend.  Check:")
        print(f"[POST]   — ESP32 and this PC on the same WiFi network?")
        print(f"[POST]   — Windows Firewall blocking inbound on port 8000?")
        print(f"[POST]   — IP in config.h matches current PC IP? (run find_server_ip.py)")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[POST] ✗ HTTP {e.code}")
        print(f"[POST]   Response body: {body}")
        print()
        if e.code == 401:
            print("[POST]   → Device not registered or API key wrong. See DB section above.")
        elif e.code == 422:
            print("[POST]   → JSON validation failed (unusual after the serialized() fix).")
            print("[POST]   → Check the payload format against the VitalsIngest schema.")
        elif e.code == 500:
            print("[POST]   → Server-side error.  Check the backend terminal for a traceback.")
    except Exception as e:
        print(f"[POST] ✗ Request error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("=" * 62)
    print("  VITA DIAGNOSTIC TOOL")
    print("  Identifies why the ESP32 cannot send data to the server")
    print("=" * 62)
    print(f"\n  API key (from config.h): {API_KEY[:20]}...")
    print(f"  Server base URL:         {SERVER_BASE}")

    check_db()
    server_ok = check_server()
    if server_ok:
        test_post()

    print(f"\n{'=' * 62}\n")
