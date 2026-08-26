# Vitality — Health & Nutrition Platform

Vitality is a complete health and nutrition monitoring platform featuring an ESP32 wearable + desk station, a FastAPI backend with computer vision meal recognition and a recommendation engine, and a frontend dashboard.

## System Architecture

```
 vita-esp32 (wearable + station)
        │  HTTPS POST /api/vitals/ingest, /api/devices/status
        ▼
 vita-backend (FastAPI + MySQL/PostgreSQL)
   ├─ auth, users, devices, vitals, meals, google_health
   ├─ food_cv            — MobileNetV2 food recognition from photos
   └─ recommendation_engine — Hybrid rule + ML engine over vitals & meals
        │  REST API (/api/...)
        ▼
 vita-frontend (Static HTML/CSS/JS)
   dashboard, food log, vitals, recommendations, profile
```

## Platform Components

### 1. ESP32 Hardware (`vita-esp32`)
- **Wearable**: Heart rate, SpO2, body temperature, step counter.
- **Station**: Ambient environment & smart scale integration.
- Copy `config.example.h` to `config.h` in device folders and configure WiFi + Device API key.

### 2. Backend API (`vita-backend`)
- Built with FastAPI, SQLAlchemy, JWT Authentication, and Pydantic.
- **Food Recognition (`food_cv`)**: Transfer-learning model (MobileNetV2) trained on meal photos for dish recognition and calorie/macro lookup.
- **Recommendation Engine (`recommendation_engine`)**: Hybrid rule-based engine combined with Isolation Forest anomaly detection and OLS trend analysis over vitals/meal history.

### 3. Web Frontend (`vita-frontend`)
- Clean HTML5/CSS3/JS dashboard featuring mobile & desktop navigation.
- Interactive food logging with camera capture/upload options, dynamic portion adjustment, and vitals visualization.

---

## Local Setup & Quick Start

### 1. Backend Setup
```bash
cd vita-backend
python -m venv .venv
.venv\Scripts\activate      # On Windows
pip install -r requirements.txt
```

Create a `.env` file (copy `.env.example`) and configure your database and JWT secret keys:
```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=vitality
JWT_SECRET_KEY=your_secret_key
CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
```

Run database initialization and start the server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
Serve `vita-frontend` with any static file server:
```bash
cd vita-frontend
python -m http.server 8080
```
Open `http://localhost:8080` in your browser.

---

## Utility & Diagnostic Tools
- Verify DB tables: `python db_setup.py verify`
- Seed demo user: `python db_setup.py seed`
- Run API smoke tests: `python tests/test_api.py`
- Test recommendation engine: `python -m recommendation_engine.test_smoke`

