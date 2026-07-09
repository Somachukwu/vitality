"""
Quick smoke-test for all Vita API endpoints.
Run: python test_api.py
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8000/api"
passed = []
failed = []


def req(method, path, body=None, headers=None):
    headers = headers or {}
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json", **headers}
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else {})


def check(label, status, data, expect_status=200, expect_key=None):
    ok = status == expect_status and (expect_key is None or expect_key in data)
    mark = "PASS" if ok else "FAIL"
    if ok:
        passed.append(label)
    else:
        failed.append((label, status, data))
    print(f"  [{mark}] {label:<48} {status}")
    return data


print("\n=== Vita API Tests ===\n")

# ── Health ────────────────────────────────────────────────────
s, d = req("GET", "/health")
check("GET  /health", s, d, 200, "status")

# ── Auth ──────────────────────────────────────────────────────
s, d = req("POST", "/auth/register", {
    "name": "Test User", "email": "testrun@vita.app",
    "password": "test1234", "age": 25, "sex": "male", "goal_type": "maintenance",
})
check("POST /auth/register", s, d, 201, "access_token")
token = d.get("access_token", "")

s, d = req("POST", "/auth/login", {"email": "testrun@vita.app", "password": "test1234"})
check("POST /auth/login", s, d, 200, "access_token")
token = d.get("access_token", token)
auth = {"Authorization": f"Bearer {token}"}

# ── Users ─────────────────────────────────────────────────────
s, d = req("GET", "/users/profile", headers=auth)
check("GET  /users/profile", s, d, 200, "id")

s, d = req("PUT", "/users/profile", {"height": 175.0, "weight": 70.0, "daily_calorie_target": 2200}, headers=auth)
check("PUT  /users/profile", s, d, 200, "height")

# ── Devices ───────────────────────────────────────────────────
s, d = req("POST", "/devices/register", {"device_uid": "AA:BB:CC:DD:EE:FF", "device_name": "My ESP32"}, headers=auth)
check("POST /devices/register", s, d, 201, "api_key")
api_key = d.get("api_key", "")
dev_id = d.get("id", 0)

s, d = req("GET", "/devices/", headers=auth)
check("GET  /devices/", s, d, 200)

# ── Vitals (ESP32 path) ───────────────────────────────────────
esp = {"X-API-Key": api_key}
s, d = req("POST", "/vitals/ingest", {
    "heart_rate": 72.0, "spo2": 98.5, "temperature": 36.6, "humidity": 45.0, "steps": 1500,
}, headers=esp)
check("POST /vitals/ingest  (ESP32 key)", s, d, 201, "id")

s, d = req("GET", "/vitals/latest", headers=auth)
check("GET  /vitals/latest", s, d, 200, "heart_rate")

s, d = req("GET", "/vitals/history?days=7", headers=auth)
check("GET  /vitals/history?days=7", s, d, 200)

# ── Meals ─────────────────────────────────────────────────────
now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
s, d = req("POST", "/meals/", {
    "meal_type": "breakfast", "logged_at": now,
    "items": [{"food_name": "Oatmeal", "portion_size": "1 cup", "calories": 300, "carbs": 54, "protein": 10, "fat": 5}],
}, headers=auth)
check("POST /meals/", s, d, 201, "id")
meal_id = d.get("id", 0)

s, d = req("GET", "/meals/", headers=auth)
check("GET  /meals/", s, d, 200)

# ── Recommendations ───────────────────────────────────────────
s2, d2 = req("POST", "/auth/login", {"email": "demo@vita.app", "password": "demo1234"})
demo_auth = {"Authorization": f"Bearer {d2.get('access_token', '')}"}

s, d = req("GET", "/recommendations/", headers=demo_auth)
check("GET  /recommendations/", s, d, 200)

if isinstance(d, list) and d:
    rec_id = d[0]["id"]
    s, d = req("PATCH", f"/recommendations/{rec_id}/read", headers=demo_auth)
    check("PATCH /recommendations/{id}/read", s, d, 200, "is_read")

# ── Cleanup ───────────────────────────────────────────────────
s, d = req("DELETE", f"/meals/{meal_id}", headers=auth)
check("DELETE /meals/{id}", s, d, 204)

s, d = req("DELETE", f"/devices/{dev_id}", headers=auth)
check("DELETE /devices/{id}", s, d, 204)

# ── Summary ───────────────────────────────────────────────────
print(f"\nResults: {len(passed)} passed, {len(failed)} failed")
if failed:
    print()
    for label, status, data in failed:
        print(f"  FAIL: {label} -> HTTP {status}: {data}")
    sys.exit(1)
else:
    print("\nAll endpoints working correctly.")
