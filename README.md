# Vitality

A health and nutrition monitoring platform: an ESP32 wearable + desk station
capture vitals, a FastAPI backend ingests them and recognizes logged meals via
computer vision, and a web frontend surfaces vitals, food logs, and
personalized recommendations back to the user.

## How it fits together

```
 vita-esp32 (wearable + station)
        │  HTTPS POST /api/vitals/ingest, /api/devices/status
        ▼
 vita-backend (FastAPI + MySQL)
   ├─ auth, users, devices, vitals, meals
   ├─ food_cv            — recognizes food from photos
   └─ recommendation_engine — rule + ML engine over vitals/meals history
        │  REST API (/api/...)
        ▼
 vita-frontend (static HTML/CSS/JS)
   dashboard, food log, vitals, recommendations, profile
```

- **vita-esp32** — Arduino sketches for two devices: a wearable (heart rate,
  SpO2, body temp, steps) and a station (humidity, weight). Both POST
  readings to the backend and share a WiFi/server config pattern — see
  `vita-esp32/vita_station/config.example.h` and
  `vita-esp32/vita_wearable/config.example.h`. Copy each to `config.h` and
  fill in your own WiFi credentials and device API key (never commit the
  real `config.h` files — they're gitignored on purpose).
- **vita-backend** — the API everything talks to. Full setup, environment
  variables, and run instructions: [`vita-backend/README.md`](vita-backend/README.md).
- **vita-frontend** — the web UI. Full structure and run instructions:
  [`vita-frontend/README.md`](vita-frontend/README.md).

## Typical local workflow

1. Start MySQL and run `vita-backend/sql/init.sql` once to create the schema.
2. Start the backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` (from `vita-backend/`).
3. Run `python vita-esp32/find_server_ip.py` to patch both ESP32 `config.h`
   files with your machine's current local IP, then flash the devices —
   only needed when your WiFi network changes.
4. Serve the frontend (`vita-frontend/`) with any static file server, e.g.
   `python -m http.server 8080`, and open it in a browser.

Tech stack details, environment variables, and testing live in each
component's own README — linked above.
