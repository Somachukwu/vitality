#pragma once

// ============================================================
//  VITA WEARABLE — Configuration
//  Sensors: MAX30102 (HR + SpO2) | MLX90614 (body temp) | MPU6050 (steps/gyro)
//  All three sensors share the I2C bus (SDA=GPIO21, SCL=GPIO22)
//
//  Copy this file to config.h and fill in your real values.
//  config.h is gitignored and will never be committed.
// ============================================================

// ── 1. WiFi ──────────────────────────────────────────────────
#define WIFI_SSID      "your-wifi-ssid"
#define WIFI_PASSWORD  "your-wifi-password"

// ── 2. Backend Server ─────────────────────────────────────────
// Run  find_server_ip.py  to get your PC's local IP.
// Use --host 0.0.0.0 when starting uvicorn so the ESP32 can reach it.
#define SERVER_INGEST_URL         "http://YOUR_PC_IP:8000/api/vitals/ingest"
#define SERVER_HEALTH_URL         "http://YOUR_PC_IP:8000/api/health"
#define SERVER_DEVICE_STATUS_URL  "http://YOUR_PC_IP:8000/api/devices/status"
#define SERVER_TIMEOUT_MS         10000

// ── 3. Device API Key (WEARABLE) ─────────────────────────────
// 1. Flash once — open Serial Monitor and copy the Chip UID
// 2. Go to Vita web app → Profile → Add Device → paste the UID
// 3. Copy the returned api_key here and reflash
#define DEVICE_API_KEY  "paste-wearable-api-key-here"

// ── 4. I2C Addresses (defaults — only change if you modified AD0/ADDR pins) ──
#define MAX30102_I2C_ADDR  0x57   // fixed, cannot be changed
#define MLX90614_I2C_ADDR  0x5A   // default; change with EEPROM command if needed
#define MPU6050_I2C_ADDR   0x68   // AD0 LOW=0x68, AD0 HIGH=0x69

// ── 5. MAX30102 Sampling ─────────────────────────────────────
#define HR_BUFFER_LEN       100   // samples per reading (100 @ 100 Hz ≈ 1 s)
#define HR_MIN_VALID        30    // bpm below this is rejected
#define HR_MAX_VALID        220   // bpm above this is rejected
#define SPO2_MIN_VALID      80    // % below this is rejected

// ── 6. MPU6050 Step Detection ────────────────────────────────
// Peak-detection pedometer: a step is counted when acceleration
// magnitude crosses STEP_HIGH_G then drops back below STEP_LOW_G.
#define STEP_HIGH_G     1.25f  // upper threshold (g-force)
#define STEP_LOW_G      0.90f  // lower threshold (g-force)
#define STEP_MIN_MS     350    // minimum ms between two steps (avoids noise)

// ── 7. Timing ────────────────────────────────────────────────
#define POST_INTERVAL_MS  30000   // send vitals every 30 s
#define MPU_POLL_MS       20      // poll MPU6050 every 20 ms for step counting

// ── 8. NTP ───────────────────────────────────────────────────
#define NTP_SERVER    "pool.ntp.org"
#define GMT_OFFSET_S  3600   // WAT = UTC+1  (Nigeria)
#define DST_OFFSET_S  0

// ── 9. Debug ─────────────────────────────────────────────────
#define SERIAL_BAUD  115200
#define LED_PIN      2       // built-in LED on most ESP32 boards

// ── 10. OLED Display (SSD1306 128×64 on I2C) ─────────────────
// Shares the I2C bus with MAX30102/MLX90614/MPU6050 — no new wiring needed.
// Required libs: Adafruit SSD1306, Adafruit GFX Library
// SD1 pin LOW = 0x3C (most modules)  |  SD1 pin HIGH = 0x3D
#define OLED_ADDR  0x3C
