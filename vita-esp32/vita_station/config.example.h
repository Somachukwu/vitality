#pragma once

// ============================================================
//  VITA STATION — Configuration
//  Sensors: DHT11 (humidity) | HX711 + Load Cell (weight — provision)
//  This device sits on a desk / bathroom scale — NOT worn.
//
//  Copy this file to config.h and fill in your real values.
//  config.h is gitignored and will never be committed.
// ============================================================

// ── 1. WiFi ──────────────────────────────────────────────────
#define WIFI_SSID      "your-wifi-ssid"
#define WIFI_PASSWORD  "your-wifi-password"

// ── 2. Backend Server ─────────────────────────────────────────
// Run  find_server_ip.py  (or start_server.bat) to keep these URLs current.
#define SERVER_INGEST_URL         "http://YOUR_PC_IP:8000/api/vitals/ingest"
#define SERVER_HEALTH_URL         "http://YOUR_PC_IP:8000/api/health"
#define SERVER_DEVICE_STATUS_URL  "http://YOUR_PC_IP:8000/api/devices/status"
#define SERVER_TIMEOUT_MS         10000

// ── 3. Device API Key (STATION) ──────────────────────────────
// Register THIS device separately from the wearable — it gets its own api_key.
// Both keys belong to the same user account.
#define DEVICE_API_KEY  "paste-station-api-key-here"

// ── 4. DHT11 ─────────────────────────────────────────────────
#define DHT_PIN         4    // data pin (add 10 kΩ pull-up to 3V3)
// Note: DHT11 resolution is 1 % RH and 1 °C — good enough for ambient humidity.

// ── 5. HX711 + Load Cell (weight scale provision) ────────────
// Set ENABLE_HX711 to 1 when you have the hardware wired.
// Set to 0 to compile without it.
#define ENABLE_HX711    0

#define HX711_DOUT_PIN  16
#define HX711_SCK_PIN   17

// Calibration: place a known weight on the scale, read the raw value,
// then: SCALE_FACTOR = raw_value / known_weight_in_kg
// Re-run calibration sketch (see comments in readWeight()) to find your value.
#define SCALE_FACTOR    420.0f
#define SCALE_OFFSET    0L        // zero/tare offset
#define WEIGHT_SAMPLES  10        // readings to average
#define WEIGHT_MIN_KG   1.0f      // ignore readings below this (empty scale)
#define WEIGHT_MAX_KG   300.0f    // ignore readings above this (sensor error)

// ── 6. Timing ────────────────────────────────────────────────
#define POST_INTERVAL_MS  30000   // send every 30 s

// ── 7. NTP ───────────────────────────────────────────────────
#define NTP_SERVER    "pool.ntp.org"
#define GMT_OFFSET_S  3600
#define DST_OFFSET_S  0

// ── 8. Debug ─────────────────────────────────────────────────
#define SERIAL_BAUD  115200
#define LED_PIN      2

// ── 9. OLED Display (SSD1306 128×64 on I2C) ──────────────────
// Wire: SDA → GPIO 21,  SCL → GPIO 22  (new connections for OLED)
// Required libs: Adafruit SSD1306, Adafruit GFX Library
// SD1 pin LOW = 0x3C (most modules)  |  SD1 pin HIGH = 0x3D
#define OLED_ADDR  0x3C
