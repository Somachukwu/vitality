# Vitality — Health, Nutrition & Vitals Telemetry Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.17-FF6F00?logo=tensorflow&logoColor=white)](https://tensorflow.org)
[![ESP32](https://img.shields.io/badge/ESP32-Arduino%2FC%2B%2B-red?logo=espressif&logoColor=white)](https://espressif.com)
[![License](https://img.shields.io/badge/License-Academic%20%2F%20Open-green)](#)

> **Vitality** is an end-to-end preventative health and nutrition monitoring platform. It combines dual ESP32 IoT hardware (Wearable + Desk Station), a FastAPI backend powered by Computer Vision (MobileNetV2) and a hybrid clinical Rule + ML Recommendation Engine, with a responsive web dashboard designed for real-time health intelligence.

---

## System Architecture

```
  ┌────────────────────────┐         ┌────────────────────────┐
  │  ESP32 Vita Wearable   │         │   ESP32 Vita Station   │
  │ (HR, SpO2, Temp, Step) │         │ (Weight Scale, Env DHT)│
  └───────────┬────────────┘         └───────────┬────────────┘
              │ HTTPS POST /api/vitals/ingest    │
              └────────────────┬─────────────────┘
                               ▼
        ┌───────────────────────────────────────────────┐
        │             FastAPI Backend (Vita)            │
        │                                               │
        │  • JWT Auth & Device API Key Auth             │
        │  • Vitals Ingest & Telemetry Aggregation      │
        │  • Food CV (MobileNetV2 Dish Recognition)     │
        │  • Recommendation Engine (Rules + Isolation   │
        │    Forest Anomaly + OLS Trend Detection)      │
        │  • Google Health Connect OAuth (Fernet)       │
        └───────┬───────────────────────────────▲───────┘
                │ REST API (/api/...)           │ Sync
                ▼                               ▼
  ┌───────────────────────────┐   ┌───────────────────────────┐
  │    Static Web Frontend    │   │      MySQL / Cloud DB     │
  │ (Dashboard, Food Log, UI) │   │ (Users, Vitals, Meals...) │
  └───────────────────────────┘   └───────────────────────────┘
```

---

## Repository File Structure

```
VITALITY/
├── README.md                          # Project documentation
├── .gitignore                         # Strict git exclusions (secrets, logs, weights)
├── start-dev.bat                      # 1-Click Windows Dev Launcher (Backend + Frontend)
│
├── vita-backend/                      # Python FastAPI application
│   ├── app/                           # Core application package
│   │   ├── core/                      # Security, encryption, and dependencies
│   │   │   ├── config.py              # Centralized settings & absolute path constants
│   │   │   ├── dependencies.py        # Auth & user context dependency injection
│   │   │   ├── encryption.py          # Fernet symmetric encryption for OAuth tokens
│   │   │   └── security.py            # Password hashing & JWT token handling
│   │   ├── database.py                # SQLAlchemy DB engine & sessionmaker
│   │   ├── main.py                    # FastAPI entrypoint, lifespan, & CORS
│   │   ├── models/                    # SQLAlchemy ORM database models
│   │   │   ├── device.py              # Registered ESP32 devices
│   │   │   ├── food_feedback.py       # CV correction logs
│   │   │   ├── google_health_token.py # Encrypted OAuth tokens
│   │   │   ├── meal.py                # Meals & individual food items
│   │   │   ├── recommendation.py      # Generated clinical & lifestyle nudges
│   │   │   ├── sleep_session.py       # Sleep tracking records
│   │   │   ├── user.py                # User profiles, goals, & health conditions
│   │   │   └── vitals.py              # Time-series telemetry readings
│   │   ├── routers/                   # REST API route handlers
│   │   │   ├── auth.py                # Registration, login, & token refresh
│   │   │   ├── devices.py             # ESP32 device pairing & heartbeat
│   │   │   ├── food_recognition.py    # Image upload & dish inference
│   │   │   ├── google_health.py       # Google Health OAuth & data ingestion
│   │   │   ├── meals.py               # Meal logging CRUD & macro totals
│   │   │   ├── recommendations.py     # 3-tier recommendation endpoints
│   │   │   ├── users.py               # User profile management
│   │   │   └── vitals.py              # Hardware ingestion & history queries
│   │   ├── schemas/                   # Pydantic validation schemas
│   │   └── services/                  # Business logic (Google Health sync, etc.)
│   │
│   ├── food_cv/                       # Computer Vision Meal Recognition package
│   │   ├── config.py                  # Model hyperparameters, classes, & paths
│   │   ├── data_prep.py               # Train/val/test dataset split pipeline
│   │   ├── evaluate.py                # Model evaluation & confusion matrices
│   │   ├── inference.py               # Single entry-point food classifier
│   │   ├── nutrition_lookup.py        # Dish-to-macro/calorie reference database
│   │   ├── train.py                   # 2-stage transfer learning training script
│   │   ├── dataset/                   # Training datasets (raw / split) [.gitkeep]
│   │   └── trained_model/             # Exported Keras weights & class indices [.gitkeep]
│   │
│   ├── recommendation_engine/         # Hybrid Intelligence Engine
│   │   ├── fusion.py                  # Telemetry & meal timeline aggregator
│   │   ├── models.py                  # Domain dataclasses & clinical target math
│   │   ├── recommendation_service.py  # Orchestration, delivery tiering, & persistence
│   │   ├── rules_engine.py            # Rule evaluator with cooldown filtering
│   │   ├── ml/                        # Machine Learning subsystems
│   │   │   ├── anomaly_detection.py   # Isolation Forest anomaly scoring
│   │   │   └── trend_detection.py     # OLS linear regression slope analysis
│   │   ├── rules/                     # Deterministic rule implementations
│   │   │   ├── correlation_rules.py   # Cross-domain rules (e.g. food vs heart rate)
│   │   │   ├── nutrition_rules.py     # Macro balance & calorie gap rules
│   │   │   ├── v1_rules.py            # Complete V1 clinical rule catalog
│   │   │   └── vitals_rules.py        # SpO2, tachycardia, & sleep rules
│   │   └── test_smoke.py              # Engine unit & pipeline test suite
│   │
│   ├── sql/                           # SQL schema migrations & seed files
│   │   └── init.sql                   # Complete relational database DDL
│   ├── tests/                         # Backend API test suite
│   │   └── test_api.py                # HTTP integration smoke tests
│   ├── uploads/meals/                 # Uploaded meal photos (served at /uploads) [.gitkeep]
│   ├── db_setup.py                    # Database verification, seed, & reset CLI
│   ├── diagnose.py                    # Hardware-to-backend connectivity diagnostic tool
│   ├── requirements.txt               # Backend Python dependencies
│   ├── .env.example                   # Sample environment configuration template
│   └── .env                           # Local environment secrets (git-ignored)
│
├── vita-frontend/                     # Responsive Client Web Application
│   ├── assets/images/                 # Brand assets, logos, and icons
│   ├── js/                            # Modular ES6 client scripts
│   │   ├── api.js                     # Dynamic environment API client (Local vs Cloud)
│   │   ├── auth.js                    # JWT storage, login/register, & guard hooks
│   │   ├── dashboard.js               # Main overview telemetry charts & summary
│   │   ├── food-log.js                # Meal photo capture, portion slider, & log UI
│   │   ├── mock.js                    # Offline simulation test data
│   │   ├── nav.js                     # Shared mobile bottom-bar & desktop sidebar
│   │   ├── profile.js                 # User profile, device pairing, & Google Health
│   │   ├── recommendations.js         # Curated 3-tier recommendation feed
│   │   ├── utils.js                   # UI notifications, date helpers, & Lucide icons
│   │   └── vitals.js                  # Time-series vitals visualization & gauge dials
│   ├── styles/                        # CSS stylesheets
│   │   └── main.css                   # Custom responsive styling & design tokens
│   ├── index.html                     # Landing page
│   ├── login.html                     # User authentication
│   ├── register.html                  # Account registration
│   ├── onboarding.html                # Initial profile & goal setup
│   ├── dashboard.html                 # Main health dashboard
│   ├── food-log.html                  # Meal logger & photo recognition
│   ├── vitals.html                    # Real-time vitals monitoring
│   ├── recommendations.html           # Curated AI insights & clinical nudges
│   └── profile.html                   # Device management & settings
│
└── vita-esp32/                        # Microcontroller Firmware (C++ / Arduino)
    ├── find_server_ip.py              # Script to auto-detect PC IP & patch firmware headers
    ├── vita_station/                  # Ambient Desk Station & Smart Scale firmware
    │   ├── vita_station.ino           # Main station sketch (HX711, DHT22, OLED)
    │   ├── config.example.h           # Configuration template
    │   └── config.h                   # Device WiFi & API key secrets (git-ignored)
    └── vita_wearable/                 # Wearable Monitor firmware
        ├── vita_wearable.ino          # Main wearable sketch (MAX30102, MLX90614, OLED)
        ├── config.example.h           # Configuration template
        └── config.h                   # Device WiFi & API key secrets (git-ignored)
```

---

## Key Features

### 1. IoT Hardware Telemetry (`vita-esp32`)
- **Wearable Device**: Continuous real-time measurement of Heart Rate (BPM), Blood Oxygen Saturation ($\text{SpO}_2$), Skin/Body Temperature (°C), and Step Count.
- **Station Device**: Smart scale body weight tracking (via load cells) and ambient room environment (Temperature & Humidity).
- **Auto-Provisioning**: Automated IP detection and patching via [`find_server_ip.py`](file:///c:/Users/HP/Desktop/VITALITY/vita-esp32/find_server_ip.py) and per-device 64-character hex API key authentication.

### 2. Computer Vision Meal Recognition (`food_cv`)
- **MobileNetV2 Architecture**: Lightweight transfer-learning model trained on Nigerian and continental dishes (Jollof Rice, Egusi, Banga, Bitterleaf, Moi Moi, Akara, etc.).
- **Automatic Nutrition Extraction**: Converts visual dish predictions into exact Calorie, Protein, Carbohydrate, and Fat amounts with confidence scoring.
- **User Correction Loop**: Stores user feedback and portion adjustments to refine future training cycles.

### 3. Clinical & Behavioral Recommendation Engine (`recommendation_engine`)
- **3-Tiered Delivery**:
  - `safety` (Critical Alerts): Immediate clinical warnings for hypoxemia ($\text{SpO}_2 < 90\%$), severe tachycardia, or extreme body temperature.
  - `primary_action` (Daily Focus): One highest-priority actionable behavior (e.g. logging remaining daily calories, bedtime consistency).
  - `supporting_insight` (Trends): Long-term context (e.g. weight trajectory vs calorie deficit over 2–4 weeks).
- **Clinical Target Modeling**: Calculates BMR and daily calorie targets via Mifflin-St Jeor and Harris-Benedict formulas with strict safety minimum floors ($1200\text{ kcal}$ female, $1500\text{ kcal}$ male).
- **Cooldown & Fatigue Suppression**: Automatic suppression logic prevents notification overload for already-acknowledged insights.

### 4. Google Health Connect Sync
- OAuth2 integration with **Fernet-encrypted token storage at rest**.
- Synchronizes background activity: active zone minutes, calories burned, floors climbed, and distance walked.

### 5. Responsive Web Interface (`vita-frontend`)
- Clean, fast, zero-bundle vanilla ES Modules architecture.
- **Smart Origin Auto-Detection**: Automatically communicates with `http://localhost:8000` when served on `localhost`, and seamlessly uses the production cloud backend when hosted online.

---

## Getting Started

### Prerequisites
- **Python 3.10+** (Python 3.11 or 3.12 recommended)
- **MySQL 8.0+** or compatible MariaDB / PostgreSQL
- **Arduino IDE** or PlatformIO (for flashing ESP32 microcontrollers)

---

### Quick Launch (Windows)

To start both the Backend API and the Static Frontend server simultaneously with one command:
```cmd
start-dev.bat
```
- **Web App**: [http://localhost:8080](http://localhost:8080)
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Manual Setup Step-by-Step

#### 1. Backend Setup (`vita-backend`)

1. Navigate to the backend directory:
   ```bash
   cd vita-backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create your `.env` configuration file:
   ```bash
   # Copy the example file
   cp .env.example .env
   ```

5. Configure `.env` with your database credentials and secret keys:
   ```ini
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=vitality

   JWT_SECRET_KEY=generate_a_random_jwt_secret_key
   SESSION_SECRET_KEY=generate_a_random_session_secret_key
   FERNET_SECRET_KEY=generate_with_Fernet_generate_key

   # Optional Cloudinary (for cloud image storage)
   CLOUDINARY_URL=

   # Google Health Connect OAuth credentials
   GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_client_secret
   GOOGLE_REDIRECT_URI=http://localhost:8000/api/google-health/callback
   ```

6. Initialize and seed the database:
   ```bash
   # Verify database connection and schema
   python db_setup.py verify

   # Seed default demo account (demo@vita.app / demo1234)
   python db_setup.py seed
   ```

7. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

#### 2. Frontend Setup (`vita-frontend`)

Serve the static frontend with any HTTP server (e.g. Python's built-in server or VS Code Live Server):

```bash
cd vita-frontend
python -m http.server 8080
```

Open [http://localhost:8080](http://localhost:8080) in your web browser.

> [!TIP]
> The frontend automatically detects local environments and routes API requests to `http://localhost:8000`. You can also manually override the API URL at any time in the browser console:
> ```javascript
> localStorage.setItem('VITA_API_URL', 'http://127.0.0.1:8000');
> ```

---

#### 3. ESP32 Hardware Setup (`vita-esp32`)

1. Copy `config.example.h` to `config.h` in both device folders:
   - `vita-esp32/vita_wearable/config.h`
   - `vita-esp32/vita_station/config.h`

2. Run the IP auto-patcher on your computer to bind your computer's local IP address into the firmware:
   ```bash
   python vita-esp32/find_server_ip.py
   ```

3. Register your device:
   - Power on the ESP32. The OLED screen displays its unique **Chip UID**.
   - Log into the Vitality web dashboard -> **Profile** -> **Add Device** and enter the Chip UID.
   - Copy the generated 64-character API key into `config.h` under `DEVICE_API_KEY`.

4. Flash the `.ino` firmware to the respective ESP32 boards using the Arduino IDE.

---

## Utility & Diagnostic Tools

The project includes purpose-built developer utilities:

| Tool | Command | Description |
| :--- | :--- | :--- |
| **System Diagnostics** | `python diagnose.py` | Tests DB connectivity, device API key registration, server health, and simulated ESP32 POST ingestion. |
| **Recommendation Engine Tests** | `python -m recommendation_engine.test_smoke` | Validates BMR floors, rule evaluations, Isolation Forest anomaly scoring, and delivery tiering. |
| **API Smoke Tests** | `python tests/test_api.py` | Runs automated end-to-end HTTP integration tests against all active endpoints. |
| **Database Tooling** | `python db_setup.py [verify\|seed\|reset]` | Inspects table schemas, seeds demo accounts, or resets test database tables. |
| **Food CV Training** | `python -m food_cv.train` | Runs 2-stage transfer learning on datasets placed in `food_cv/dataset/raw/`. |

---

## API Documentation Overview

FastAPI provides interactive Swagger documentation automatically:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Primary API Routes

```
Authentication & Users
  POST   /api/auth/register            # Create account & return JWT
  POST   /api/auth/login               # User login
  GET    /api/users/me                 # Current user profile & goals
  PATCH  /api/users/me                 # Update user bio/targets

Hardware & Vitals Telemetry
  POST   /api/vitals/ingest            # ESP32 time-series ingestion (X-API-Key authenticated)
  GET    /api/vitals/latest            # Most recent vitals reading
  GET    /api/vitals/history           # Time-range telemetry history
  POST   /api/devices/register         # Pair a new wearable or station
  GET    /api/devices/                 # List paired hardware & last seen status

Computer Vision & Nutrition
  POST   /api/food/recognize           # Upload meal photo for AI classification
  POST   /api/meals/                   # Create meal entry with macro breakdown
  GET    /api/meals/today              # Aggregated today's nutrition totals

Recommendation Intelligence
  GET    /api/recommendations/         # List active recommendation entries
  GET    /api/recommendations/grouped  # Curated 3-tier delivery (Safety, Primary, Insight)
  POST   /api/recommendations/{id}/dismiss # Acknowledge recommendation & trigger cooldown

Google Health Connect
  GET    /api/google-health/authorize  # Start OAuth2 authorization flow
  GET    /api/google-health/callback   # OAuth2 exchange & token storage
  POST   /api/google-health/sync       # Synchronize activity data
```

---

## Security & Privacy Highlights

- **Encrypted Health Tokens**: Google Health Connect refresh tokens are symmetrically encrypted at rest using Python's `cryptography.fernet` before database persistence.
- **Password Security**: User credentials are protected using salted bcrypt hashes with `passlib`.
- **Hardware Isolation**: ESP32 devices communicate using isolated 64-character cryptographic tokens verified on each ingestion payload.
- **Git Security**: Sensitive environment configurations (`.env`), hardware credentials (`config.h`), logs, virtual environments, and raw dataset weights are strictly excluded via `.gitignore`.

---

## Credits & Acknowledgements

Developed as a comprehensive IoT, AI, and preventative healthcare engineering project by students of **Nnamdi Azikiwe University, Awka (2026)**.
