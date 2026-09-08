#pragma once

// ============================================================
//  VITA STATION — Configuration Template
//  Smart bathroom scale. Reads body weight via HX711 + load cell
//  and POSTs to the Vita backend over WiFi.
//
//  Copy this file to config.h and fill in your real values.
//  config.h is git-ignored and will never be committed.
// ============================================================

// ── 1. WiFi ──────────────────────────────────────────────────
#define WIFI_SSID      "your-wifi-ssid"
#define WIFI_PASSWORD  "your-wifi-password"

// ── 2. Backend Server ─────────────────────────────────────────
// Run  vita-esp32/find_server_ip.py  to get the correct IP.
#define SERVER_INGEST_URL   "http://YOUR_PC_IP:8000/api/vitals/ingest"
#define SERVER_TIMEOUT_MS   10000

// ── 3. Device API Key ─────────────────────────────────────────
// Register this device in the Vita app to get an api_key.
#define DEVICE_API_KEY  "paste-station-api-key-here"

// ── 4. HX711 + Load Cell ──────────────────────────────────────
// Set ENABLE_HX711 to 1 once the hardware is wired and calibrated.
#define ENABLE_HX711    0

//  Wiring:
//    ESP32 GPIO 3  ----> HX711 DOUT
//    ESP32 GPIO 2  ----> HX711 SCK
//    HX711 VCC     ----> ESP32 5V  (NEVER 3.3V — HX711 requires 5V)
//    HX711 GND     ----> ESP32 GND
//    Load cell E+/E-  -> HX711 E+/E-   (excitation wires)
//    Load cell A+/A-  -> HX711 A+/A-   (signal wires)
#define HX711_DOUT_PIN  3
#define HX711_SCK_PIN   2

// Calibration values — run vita_scale_calibrate.ino to find these.
// Step 1: note the raw tare value (nothing on scale)  -> SCALE_OFFSET
// Step 2: place known weight, enter kg -> SCALE_FACTOR is printed for you
#define SCALE_FACTOR    420.0f    // <- replace with value from calibration sketch
#define SCALE_OFFSET    0L        // <- replace with tare raw value from calibration sketch
#define WEIGHT_SAMPLES  10        // readings averaged per POST
#define WEIGHT_MIN_KG   1.0f      // readings below this are ignored (empty scale)
#define WEIGHT_MAX_KG   300.0f    // readings above this are ignored (sensor fault)

// ── 5. Timing ────────────────────────────────────────────────
#define POST_INTERVAL_MS  30000   // send weight to server every 30 s

// ── 6. NTP (time sync) ────────────────────────────────────────
#define NTP_SERVER    "pool.ntp.org"
#define GMT_OFFSET_S  3600        // UTC+1 (WAT, West Africa Time)
#define DST_OFFSET_S  0

// ── 7. Debug ─────────────────────────────────────────────────
#define SERIAL_BAUD  115200
#define LED_PIN      2            // built-in LED on most ESP32 DevKit boards
