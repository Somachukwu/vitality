// ============================================================
//  VITA STATION — ESP32 Firmware  (Scale-only build)
//  Reads body weight via HX711 + load cell and POSTs to the
//  Vita backend every POST_INTERVAL_MS milliseconds.
//
//  Output channels:
//    • Serial Monitor  — live readings + status (115200 baud)
//    • Vita backend    — weight POSTed as JSON to /api/vitals/ingest
//
//  Required libraries (Arduino IDE > Tools > Manage Libraries):
//    • ArduinoJson           by Benoit Blanchon  v6.x
//    • HX711 Arduino Library by bogde
//
//  Wiring:
//    ESP32 GPIO 3  ----> HX711 DOUT
//    ESP32 GPIO 2  ----> HX711 SCK
//    HX711 VCC     ----> ESP32 5V  (NEVER 3.3V)
//    HX711 GND     ----> ESP32 GND
//    Load cell E+/E-  -> HX711 E+/E-
//    Load cell A+/A-  -> HX711 A+/A-
//
//  Before flashing:
//    1. Run vita_scale_calibrate.ino to get SCALE_FACTOR + SCALE_OFFSET
//    2. Fill in config.h (WiFi, API key, calibration values, ENABLE_HX711=1)
// ============================================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"

#if ENABLE_HX711
  #include <HX711.h>
  HX711 scale;
  bool  scaleReady = false;
#endif

// ── State ─────────────────────────────────────────────────────
unsigned long lastPostMs = 0;
bool          ntpSynced  = false;

// ─────────────────────────────────────────────────────────────
//  LED helpers
// ─────────────────────────────────────────────────────────────
void ledOn()  { digitalWrite(LED_PIN, HIGH); }
void ledOff() { digitalWrite(LED_PIN, LOW); }
void ledBlink(int n, int ms = 120) {
  for (int i = 0; i < n; i++) { ledOn(); delay(ms); ledOff(); delay(ms); }
}

// ─────────────────────────────────────────────────────────────
//  Utilities
// ─────────────────────────────────────────────────────────────
String isoTimestamp() {
  if (!ntpSynced) return "";
  struct tm t;
  if (!getLocalTime(&t)) return "";
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &t);
  return String(buf);
}

String chipUID() {
  uint64_t mac = ESP.getEfuseMac();
  char buf[18];
  snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
    (uint8_t)mac, (uint8_t)(mac >> 8),  (uint8_t)(mac >> 16),
    (uint8_t)(mac >> 24), (uint8_t)(mac >> 32), (uint8_t)(mac >> 40));
  return String(buf);
}

// ─────────────────────────────────────────────────────────────
//  WiFi
// ─────────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    Serial.print(".");
    tries++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n[WiFi] FAILED — restarting in 5 s");
    delay(5000);
    ESP.restart();
  }

  Serial.printf("\n[WiFi] Connected — IP: %s\n", WiFi.localIP().toString().c_str());
  ledBlink(3);
}

void ensureWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Lost — reconnecting...");
    connectWiFi();
  }
}

// ─────────────────────────────────────────────────────────────
//  NTP
// ─────────────────────────────────────────────────────────────
void syncNTP() {
  configTime(GMT_OFFSET_S, DST_OFFSET_S, NTP_SERVER);
  Serial.print("[NTP]  Syncing");
  struct tm t; int tries = 0;
  while (!getLocalTime(&t) && tries < 20) { delay(500); Serial.print("."); tries++; }
  if (getLocalTime(&t)) {
    ntpSynced = true;
    Serial.printf("\n[NTP]  Synced: %s", asctime(&t));
  } else {
    Serial.println("\n[NTP]  Failed — server will timestamp readings");
  }
}

// ─────────────────────────────────────────────────────────────
//  HX711 — Weight
// ─────────────────────────────────────────────────────────────
#if ENABLE_HX711

void initHX711() {
  scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
  scale.set_scale(SCALE_FACTOR);
  scale.set_offset(SCALE_OFFSET);

  if (scale.is_ready()) {
    scaleReady = true;
    Serial.println("[HX711] Ready");
    Serial.printf("[HX711] Scale factor: %.4f  Offset: %ld\n", (float)SCALE_FACTOR, (long)SCALE_OFFSET);
  } else {
    Serial.println("[HX711] NOT READY — check DOUT=GPIO3, SCK=GPIO2, VCC=5V");
  }
}

bool readWeight(float& weightKg) {
  weightKg = NAN;
  if (!scaleReady || !scale.is_ready()) {
    Serial.println("[HX711] Scale not ready");
    return false;
  }

  float kg = scale.get_units(WEIGHT_SAMPLES);

  if (kg < WEIGHT_MIN_KG || kg > WEIGHT_MAX_KG) {
    Serial.printf("[HX711] Out of range: %.3f kg (nothing on scale, or calibration needed)\n", kg);
    return false;
  }

  weightKg = kg;
  Serial.printf("[HX711] Weight: %.2f kg\n", weightKg);
  return true;
}

#endif  // ENABLE_HX711

// ─────────────────────────────────────────────────────────────
//  HTTP POST to Vita backend
// ─────────────────────────────────────────────────────────────
void postWeight(float weightKg) {
  ensureWiFi();

  if (isnan(weightKg)) {
    Serial.println("[HTTP]  No valid weight to post — skipping");
    return;
  }

  HTTPClient http;
  http.begin(SERVER_INGEST_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key",    DEVICE_API_KEY);
  http.setTimeout(SERVER_TIMEOUT_MS);

  StaticJsonDocument<128> doc;
  doc["weight"] = round(weightKg * 10.0f) / 10.0f;   // 1 decimal place

  String ts = isoTimestamp();
  if (ts.length()) doc["recorded_at"] = ts;

  String body;
  serializeJson(doc, body);

  Serial.printf("[HTTP]  POST %s\n[HTTP]  Body: %s\n", SERVER_INGEST_URL, body.c_str());

  ledOn();
  int code = http.POST(body);
  ledOff();

  if (code == 201) {
    Serial.println("[HTTP]  201 Created — weight saved OK");
    ledBlink(2, 60);
  } else if (code > 0) {
    Serial.printf("[HTTP]  Error %d: %s\n", code, http.getString().c_str());
  } else {
    Serial.printf("[HTTP]  Connection failed: %s\n", HTTPClient::errorToString(code).c_str());
  }

  http.end();
}

// ─────────────────────────────────────────────────────────────
//  Setup
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);
  pinMode(LED_PIN, OUTPUT);
  ledOff();

  Serial.println();
  Serial.println("============================================");
  Serial.println("  VITA STATION — Weight Scale");
  Serial.println("============================================");

  String uid = chipUID();
  Serial.printf("  Chip UID : %s\n", uid.c_str());
  Serial.println("  Register this UID in the Vita app to get your API key");
  Serial.println();

  connectWiFi();
  syncNTP();

#if ENABLE_HX711
  initHX711();
  if (scaleReady) {
    Serial.println("[Scale] HX711 ready — will post weight every " + String(POST_INTERVAL_MS / 1000) + " s");
  } else {
    Serial.println("[Scale] HX711 not found — only WiFi/NTP active");
  }
#else
  Serial.println("[Scale] HX711 disabled (ENABLE_HX711=0 in config.h)");
  Serial.println("        Run vita_scale_calibrate.ino first, then set ENABLE_HX711=1");
#endif

  Serial.println();
  Serial.printf("  Posting to: %s\n", SERVER_INGEST_URL);
  Serial.printf("  Interval  : %d s\n\n", POST_INTERVAL_MS / 1000);

  ledBlink(5, 80);
}

// ─────────────────────────────────────────────────────────────
//  Loop
// ─────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();
  if (now - lastPostMs < POST_INTERVAL_MS) return;
  lastPostMs = now;

  Serial.println("--------------------------------------------");

#if ENABLE_HX711
  float weight = NAN;
  readWeight(weight);
  postWeight(weight);
#else
  Serial.println("[Loop]  HX711 disabled — nothing to post");
#endif

  Serial.println("--------------------------------------------\n");
}
