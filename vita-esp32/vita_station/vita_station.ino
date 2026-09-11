// ============================================================
//  VITA STATION — ESP32 Firmware
//  Reads body weight via HX711 + load cell and POSTs to the
//  Vita backend every POST_INTERVAL_MS milliseconds.
//
//  Hardware Pinout:
//    • ESP32 GPIO 19 ----> HX711 DOUT
//    • ESP32 GPIO 18 ----> HX711 SCK
//    • ESP32 GPIO 2  ----> Status LED (Onboard LED)
//    • HX711 VCC     ----> ESP32 5V
//    • HX711 GND     ----> ESP32 GND
//
//  LED Signals:
//    • 3 blinks : Successfully connected to Wi-Fi
//    • 2 blinks : Sending data to backend
//
//  Required libraries:
//    • ArduinoJson           by Benoit Blanchon  v6.x
//    • HX711 Arduino Library by bogde
// ============================================================

#include <WiFi.h>
#include <WiFiClientSecure.h>
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
//  LED Helper
// ─────────────────────────────────────────────────────────────
void ledBlink(int count, int delayMs = 150) {
  for (int i = 0; i < count; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(delayMs);
    digitalWrite(LED_PIN, LOW);
    delay(delayMs);
  }
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
//  Simple WLAN Connection
// ─────────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.printf("\n[WiFi] Connecting to %s", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n[WiFi] Connected successfully!");
  Serial.print("[WiFi] IP Address: ");
  Serial.println(WiFi.localIP());

  // Blink 3 times upon successful Wi-Fi connection
  ledBlink(3, 200);
}

void ensureWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
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
    Serial.printf("[HX711] NOT READY — check DOUT=GPIO%d, SCK=GPIO%d, VCC=5V\n", HX711_DOUT_PIN, HX711_SCK_PIN);
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
//  HTTP POST to Vita backend(s)
// ─────────────────────────────────────────────────────────────
bool sendPayload(const char* targetUrl, const String& jsonBody) {
  if (!targetUrl || strlen(targetUrl) == 0) return false;

  Serial.printf("[HTTP]  Target: %s\n", targetUrl);

  HTTPClient http;
  bool isHttps = (strncmp(targetUrl, "https://", 8) == 0);
  bool success = false;

  // Blink LED 2 times when sending data to backend
  ledBlink(2, 120);

  if (isHttps) {
    WiFiClientSecure secClient;
    secClient.setInsecure(); // Connect to Render cloud without heavy CA bundle
    if (http.begin(secClient, targetUrl)) {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-API-Key",    DEVICE_API_KEY);
      http.setTimeout(SERVER_TIMEOUT_MS);

      int code = http.POST(jsonBody);
      if (code == 201) {
        Serial.printf("[HTTP]  201 Created — saved OK (%s)\n", targetUrl);
        success = true;
      } else if (code > 0) {
        Serial.printf("[HTTP]  Error %d from %s: %s\n", code, targetUrl, http.getString().c_str());
      } else {
        Serial.printf("[HTTP]  Failed connecting to %s: %s\n", targetUrl, HTTPClient::errorToString(code).c_str());
      }
      http.end();
    } else {
      Serial.printf("[HTTP]  Failed to initialize HTTPS connection to %s\n", targetUrl);
    }
  } else {
    WiFiClient client;
    if (http.begin(client, targetUrl)) {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-API-Key",    DEVICE_API_KEY);
      http.setTimeout(SERVER_TIMEOUT_MS);

      int code = http.POST(jsonBody);
      if (code == 201) {
        Serial.printf("[HTTP]  201 Created — saved OK (%s)\n", targetUrl);
        success = true;
      } else if (code > 0) {
        Serial.printf("[HTTP]  Error %d from %s: %s\n", code, targetUrl, http.getString().c_str());
      } else {
        Serial.printf("[HTTP]  Failed connecting to %s: %s\n", targetUrl, HTTPClient::errorToString(code).c_str());
      }
      http.end();
    } else {
      Serial.printf("[HTTP]  Failed to initialize HTTP connection to %s\n", targetUrl);
    }
  }

  return success;
}

void postWeight(float weightKg) {
  ensureWiFi();

  if (isnan(weightKg)) {
    Serial.println("[HTTP]  No valid weight to post — skipping");
    return;
  }

  StaticJsonDocument<128> doc;
  doc["weight"] = round(weightKg * 10.0f) / 10.0f;   // 1 decimal place

  String ts = isoTimestamp();
  if (ts.length()) doc["recorded_at"] = ts;

  String body;
  serializeJson(doc, body);
  Serial.printf("[HTTP]  Payload: %s\n", body.c_str());

#if BACKEND_SYNC_MODE == 1
  // DUAL POST: Cloud (Primary) + Local (Secondary)
  Serial.println("[Sync] Sending to Cloud backend (Primary)...");
  bool cloudOk = sendPayload(CLOUD_INGEST_URL, body);
  Serial.println("[Sync] Sending to Localhost backend (Secondary)...");
  bool localOk = sendPayload(LOCAL_INGEST_URL, body);
  if (cloudOk || localOk) {
    Serial.println("[Sync] Weight delivery completed!");
  } else {
    Serial.println("[Sync] Warning: Could not reach either backend.");
  }

#elif BACKEND_SYNC_MODE == 2
  // FAILOVER: Try Cloud first (Primary); if Cloud is offline, fallback to Local (Secondary)
  Serial.println("[Sync] Trying Cloud backend (Primary)...");
  bool cloudOk = sendPayload(CLOUD_INGEST_URL, body);
  if (!cloudOk) {
    Serial.println("[Sync] Cloud unavailable. Falling back to Localhost backend...");
    sendPayload(LOCAL_INGEST_URL, body);
  }

#elif BACKEND_SYNC_MODE == 3
  // CLOUD ONLY
  sendPayload(CLOUD_INGEST_URL, body);

#elif BACKEND_SYNC_MODE == 4
  // LOCAL ONLY
  sendPayload(LOCAL_INGEST_URL, body);

#else
  // Default: Cloud primary
  sendPayload(CLOUD_INGEST_URL, body);
#endif
}

// ─────────────────────────────────────────────────────────────
//  Setup
// ─────────────────────────────────────────────────────────────
void testBackendConnections() {
  Serial.println("\n[Test] Probing backend connectivity...");

#if BACKEND_SYNC_MODE == 1 || BACKEND_SYNC_MODE == 2 || BACKEND_SYNC_MODE == 3
  {
    Serial.printf("[Test] Cloud probe [Primary] (%s)... ", CLOUD_INGEST_URL);
    HTTPClient http;
    WiFiClientSecure secClient;
    secClient.setInsecure();
    if (http.begin(secClient, CLOUD_INGEST_URL)) {
      http.setTimeout(8000);
      int code = http.GET();
      if (code > 0) {
        Serial.printf("REACHABLE (HTTP %d)\n", code);
      } else {
        Serial.printf("UNREACHABLE (%s)\n", HTTPClient::errorToString(code).c_str());
      }
      http.end();
    }
  }
#endif

#if BACKEND_SYNC_MODE == 1 || BACKEND_SYNC_MODE == 2 || BACKEND_SYNC_MODE == 4
  {
    Serial.printf("[Test] Localhost probe [Secondary] (%s)... ", LOCAL_INGEST_URL);
    HTTPClient http;
    WiFiClient client;
    if (http.begin(client, LOCAL_INGEST_URL)) {
      http.setTimeout(4000);
      int code = http.GET();
      if (code > 0) {
        Serial.printf("REACHABLE (HTTP %d)\n", code);
      } else {
        Serial.printf("UNREACHABLE (%s)\n", HTTPClient::errorToString(code).c_str());
        Serial.println("       Tip: Ensure PC and ESP32 are on the same network,");
        Serial.println("       and run backend with: uvicorn app.main:app --host 0.0.0.0 --port 8000");
      }
      http.end();
    }
  }
#endif

  Serial.println("[Test] Diagnostic check complete.\n");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);

  // Initialize LED Pin
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

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
  testBackendConnections();

#if ENABLE_HX711
  initHX711();
  if (scaleReady) {
    Serial.println("[Scale] HX711 ready — will post weight every " + String(POST_INTERVAL_MS / 1000) + " s");
  } else {
    Serial.println("[Scale] HX711 not found — only WiFi/NTP active");
  }
#else
  Serial.println("[Scale] HX711 disabled (ENABLE_HX711=0 in config.h)");
#endif

  Serial.println();
  Serial.printf("  Cloud backend [Primary]   : %s\n", CLOUD_INGEST_URL);
  Serial.printf("  Local backend [Secondary] : %s\n", LOCAL_INGEST_URL);
  Serial.printf("  Sync mode                 : %d  (1=Dual, 2=Cloud Failover, 3=Cloud Only, 4=Local Only)\n", BACKEND_SYNC_MODE);
  Serial.printf("  Interval                  : %d s\n\n", POST_INTERVAL_MS / 1000);
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
