// ============================================================
//  VITA STATION — ESP32 Firmware
//  Stationary device (desk / bathroom). Reads ambient humidity
//  and optionally body weight, then POSTs to the Vita backend.
//
//  Sensors:
//    • DHT11       — Ambient humidity (GPIO 4)
//    • HX711 + Load Cell — Body weight (GPIO 16/17) [PROVISION]
//                          Set ENABLE_HX711=1 in config.h when ready
//    • SSD1306 OLED — 128×64 status display (I2C: SDA=GPIO21, SCL=GPIO22)
//
//  Required libraries (Arduino IDE → Tools → Manage Libraries):
//    • ArduinoJson            by Benoit Blanchon   v6.x
//    • DHT sensor library     by Adafruit
//    • Adafruit Unified Sensor by Adafruit
//    • Adafruit SSD1306       by Adafruit
//    • Adafruit GFX Library   by Adafruit
//    • HX711 Arduino Library  by bogde  (only needed if ENABLE_HX711=1)
//
//  Wiring:
//  ┌──────────────┬─────────────────────────────────────────┐
//  │ ESP32 Pin    │ Connected to                            │
//  ├──────────────┼─────────────────────────────────────────┤
//  │ GPIO 4       │ DHT11 DATA  (+ 10 kΩ pull-up to 3V3)   │
//  │ 3V3          │ DHT11 VCC                               │
//  │ GND          │ DHT11 GND                               │
//  │              │  ── OLED SSD1306 ──                     │
//  │ GPIO 21 (SDA)│ OLED SDA                                │
//  │ GPIO 22 (SCL)│ OLED SCL                                │
//  │ 3V3          │ OLED VCC                                │
//  │ GND          │ OLED GND                                │
//  │              │  ── HX711 (provision) ──                │
//  │ GPIO 16      │ HX711 DOUT                              │
//  │ GPIO 17      │ HX711 SCK                               │
//  │ 5V           │ HX711 VCC  (needs 5V, not 3.3V)        │
//  │ GND          │ HX711 GND                               │
//  │              │  ── Load Cell wires → HX711 ──          │
//  │ HX711 E+/E-  │ Load cell excitation wires              │
//  │ HX711 A+/A-  │ Load cell signal wires                  │
//  └──────────────┴─────────────────────────────────────────┘
//
//  HX711 Calibration (one-time):
//    1. Set ENABLE_HX711=1 and flash this sketch
//    2. Open Serial Monitor — note the raw value with nothing on scale (tare)
//    3. Place a known weight (e.g. 1 kg), note new raw value
//    4. SCALE_FACTOR = (raw_with_weight - tare) / weight_in_kg
//    5. Set SCALE_FACTOR and SCALE_OFFSET in config.h and reflash
// ============================================================

#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <time.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "config.h"

// HX711 included only if enabled
#if ENABLE_HX711
  #include <HX711.h>
  HX711 scale;
  bool scaleReady = false;
#endif

// ── Sensor objects ────────────────────────────────────────────
DHT dht(DHT_PIN, DHT11);

// ── OLED ─────────────────────────────────────────────────────
Adafruit_SSD1306 display(128, 64, &Wire, -1);
bool oledReady = false;

// ── State ────────────────────────────────────────────────────
unsigned long lastPostMs    = 0;
bool          ntpSynced     = false;

// Last reading cache — used by oledRefreshData()
String lastPostStatus = "--";
String lastPostTime   = "--:--:--";
float  lastHumidity   = NAN;
float  lastAmbTemp    = NAN;
float  lastWeight     = NAN;

// ─────────────────────────────────────────────────────────────
//  LED helpers
// ─────────────────────────────────────────────────────────────

void ledOn()  { digitalWrite(LED_PIN, HIGH); }
void ledOff() { digitalWrite(LED_PIN, LOW); }
void ledBlink(int n, int ms = 120) {
  for (int i = 0; i < n; i++) { ledOn(); delay(ms); ledOff(); delay(ms); }
}

// ─────────────────────────────────────────────────────────────
//  OLED helpers
// ─────────────────────────────────────────────────────────────

// Draw inverted title bar at y=0..10
static void _oledHeader(const char* label) {
  display.fillRect(0, 0, 128, 11, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK);
  display.setCursor(2, 2);
  display.print(label);
}

// General-purpose status screen: title + up to 4 body lines
void oledShow(const char* title,
              const char* l1 = nullptr, const char* l2 = nullptr,
              const char* l3 = nullptr, const char* l4 = nullptr) {
  if (!oledReady) return;
  display.clearDisplay();
  _oledHeader(title);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  const int8_t ys[4] = {14, 25, 36, 47};
  const char*  ls[4] = {l1, l2, l3, l4};
  for (int i = 0; i < 4; i++) {
    if (ls[i]) { display.setCursor(0, ys[i]); display.print(ls[i]); }
  }
  display.display();
}

// Live data dashboard — shown during normal operation
void oledRefreshData() {
  if (!oledReady) return;
  display.clearDisplay();

  // Inverted header with live clock
  display.fillRect(0, 0, 128, 11, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK);
  display.setCursor(2, 2);
  display.print("VITA STATION");
  if (ntpSynced) {
    struct tm t;
    if (getLocalTime(&t)) {
      char tbuf[6];
      strftime(tbuf, sizeof(tbuf), "%H:%M", &t);
      display.setCursor(92, 2);
      display.print(tbuf);
    }
  }

  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // Row 1 — Humidity + Ambient Temp
  display.setCursor(0, 14);
  if (!isnan(lastHumidity)) {
    char buf[22];
    snprintf(buf, sizeof(buf), "Hum:%.0f%%  Tmp:%.0fC", lastHumidity, lastAmbTemp);
    display.print(buf);
  } else {
    display.print("Hum:--   Tmp:--");
  }

  // Row 2 — Weight
  display.setCursor(0, 25);
#if ENABLE_HX711
  if (!isnan(lastWeight)) {
    char buf[18];
    snprintf(buf, sizeof(buf), "Wt: %.1f kg", lastWeight);
    display.print(buf);
  } else {
    display.print("Wt: --");
  }
#else
  display.print("Wt: (disabled)");
#endif

  // Divider
  display.drawLine(0, 38, 127, 38, SSD1306_WHITE);

  // Row 3 — Last POST result + timestamp
  display.setCursor(0, 42);
  {
    char buf[22];
    snprintf(buf, sizeof(buf), "Sent:%-4s  %s",
             lastPostStatus.c_str(), lastPostTime.c_str());
    display.print(buf);
  }

  display.display();
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
    (uint8_t)mac, (uint8_t)(mac>>8), (uint8_t)(mac>>16),
    (uint8_t)(mac>>24), (uint8_t)(mac>>32), (uint8_t)(mac>>40));
  return String(buf);
}

// ─────────────────────────────────────────────────────────────
//  WiFi + NTP
// ─────────────────────────────────────────────────────────────

void connectWiFi() {
  char ssidLine[22];
  snprintf(ssidLine, sizeof(ssidLine), "%.21s", WIFI_SSID);

  oledShow("VITA STATION", "Connecting to WiFi:", ssidLine, "Please wait...");
  Serial.printf("\n[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    Serial.print(".");
    tries++;
    if (tries % 4 == 0) {
      char tryLine[22];
      snprintf(tryLine, sizeof(tryLine), "Trying... %ds", tries / 2);
      oledShow("VITA STATION", "Connecting to WiFi:", ssidLine, tryLine);
    }
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n[WiFi] Failed — restarting in 5 s");
    oledShow("VITA STATION", "WiFi FAILED!", "Restarting in 5s...");
    delay(5000);
    ESP.restart();
  }

  Serial.printf("\n[WiFi] Connected  IP: %s\n", WiFi.localIP().toString().c_str());
  char ipLine[22];
  snprintf(ipLine, sizeof(ipLine), "IP: %s", WiFi.localIP().toString().c_str());
  oledShow("VITA STATION", "WiFi Connected!", ssidLine, ipLine);
  delay(2000);
  ledBlink(3);
}

void ensureWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Lost — reconnecting");
    oledShow("VITA STATION", "WiFi lost!", "Reconnecting...");
    connectWiFi();
  }
}

void syncNTP() {
  oledShow("VITA STATION", "Syncing time...", NTP_SERVER);
  configTime(GMT_OFFSET_S, DST_OFFSET_S, NTP_SERVER);
  Serial.print("[NTP]  Syncing");
  struct tm t; int tries = 0;
  while (!getLocalTime(&t) && tries < 20) { delay(500); Serial.print("."); tries++; }
  if (getLocalTime(&t)) {
    ntpSynced = true;
    Serial.printf("\n[NTP]  Synced: %s", asctime(&t));
    char timeLine[22];
    strftime(timeLine, sizeof(timeLine), "%d %b  %H:%M:%S", &t);
    oledShow("VITA STATION", "Time Synced!", timeLine);
    delay(2000);
  } else {
    Serial.println("\n[NTP]  Failed — server will timestamp");
    oledShow("VITA STATION", "NTP sync failed!", "Server will timestamp");
    delay(1500);
  }
}

// ─────────────────────────────────────────────────────────────
//  DHT11 — Ambient Humidity
// ─────────────────────────────────────────────────────────────

// Reads humidity from DHT11.
// Note: DHT11 needs at least 1 second between reads.
// Temperature from DHT11 is also read here as ambient reference —
// body temperature is handled by the wearable (MLX90614).
bool readDHT11(float& humidity, float& ambientTemp) {
  humidity    = NAN;
  ambientTemp = NAN;

  // DHT11 takes ~250 ms to stabilise after power-on; wait if needed
  delay(300);

  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h)) {
    Serial.println("[DHT11] Humidity read failed — check wiring and pull-up resistor");
    return false;
  }
  humidity    = h;
  ambientTemp = isnan(t) ? NAN : t;

  Serial.printf("[DHT11] Humidity: %.0f%%   Ambient temp: %.0f°C\n", h, t);
  return true;
}

// ─────────────────────────────────────────────────────────────
//  HX711 — Weight (provision)
// ─────────────────────────────────────────────────────────────

#if ENABLE_HX711

void initHX711() {
  scale.begin(HX711_DOUT_PIN, HX711_SCK_PIN);
  scale.set_scale(SCALE_FACTOR);
  scale.set_offset(SCALE_OFFSET);

  if (scale.is_ready()) {
    scaleReady = true;
    // Print raw value so you can calibrate
    Serial.printf("[HX711] Ready  raw_zero=%.0f\n", scale.read_average(5));
    Serial.println("[HX711] Place known weight to calibrate SCALE_FACTOR in config.h");
  } else {
    Serial.println("[HX711] Not ready — check DOUT/SCK wiring and 5V power");
  }
}

bool readHX711(float& weightKg) {
  weightKg = NAN;
  if (!scaleReady || !scale.is_ready()) {
    Serial.println("[HX711] Scale not ready");
    return false;
  }

  float raw = scale.get_units(WEIGHT_SAMPLES);
  if (raw < WEIGHT_MIN_KG || raw > WEIGHT_MAX_KG) {
    Serial.printf("[HX711] Reading out of range: %.2f kg — check calibration or no load detected\n", raw);
    return false;
  }
  weightKg = raw;
  Serial.printf("[HX711] Weight: %.2f kg\n", weightKg);
  return true;
}

#endif  // ENABLE_HX711

// ─────────────────────────────────────────────────────────────
//  HTTP POST to Vita backend
// ─────────────────────────────────────────────────────────────

void postVitals(float humidity, float weight) {
  ensureWiFi();

  if (isnan(humidity) && isnan(weight)) {
    Serial.println("[HTTP] Nothing to post — all readings failed");
    lastPostStatus = "SKIP";
    oledRefreshData();
    return;
  }

  HTTPClient http;
  http.begin(SERVER_INGEST_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key",    DEVICE_API_KEY);
  http.setTimeout(SERVER_TIMEOUT_MS);

  StaticJsonDocument<128> doc;
  if (!isnan(humidity)) doc["humidity"] = humidity;
  if (!isnan(weight))   doc["weight"]   = weight;

  String ts = isoTimestamp();
  if (ts.length())      doc["recorded_at"] = ts;

  String body;
  serializeJson(doc, body);

  Serial.printf("[HTTP] POST → %s\n[HTTP] Body: %s\n", SERVER_INGEST_URL, body.c_str());

  // Show "Sending..." with what we're about to transmit
  {
    char l1[22], l2[22];
    snprintf(l1, sizeof(l1), "Hum:%.0f%%  Tmp:%.0fC",
             isnan(humidity) ? 0.0f : humidity,
             isnan(lastAmbTemp) ? 0.0f : lastAmbTemp);
    snprintf(l2, sizeof(l2), "Wt:%s",
             isnan(weight) ? "--" : (String(weight, 1) + " kg").c_str());
    oledShow("VITA STATION", "Sending to server...", l1, l2);
  }

  ledOn();
  int code = http.POST(body);
  ledOff();

  if (code == 201) {
    Serial.println("[HTTP] 201 Created — vitals saved ✓");
    lastPostStatus = "OK";
  } else if (code > 0) {
    Serial.printf("[HTTP] Error %d: %s\n", code, http.getString().c_str());
    lastPostStatus = "ERR";
  } else {
    Serial.printf("[HTTP] Connection failed: %s\n", HTTPClient::errorToString(code).c_str());
    lastPostStatus = "FAIL";
  }

  // Record post time for OLED footer
  if (ntpSynced) {
    struct tm t;
    if (getLocalTime(&t)) {
      char tbuf[9];
      strftime(tbuf, sizeof(tbuf), "%H:%M:%S", &t);
      lastPostTime = String(tbuf);
    }
  }

  http.end();
  if (code == 201) ledBlink(2, 60);

  oledRefreshData();  // Switch to live dashboard showing what was just sent
}

// ─────────────────────────────────────────────────────────────
//  Arduino setup / loop
// ─────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(1000);
  pinMode(LED_PIN, OUTPUT);
  ledOff();

  Serial.println("╔══════════════════════════════════════════╗");
  Serial.println("║   VITA STATION — ESP32 Firmware          ║");
  Serial.println("╚══════════════════════════════════════════╝");

  Wire.begin();  // SDA=GPIO21, SCL=GPIO22

  // Init OLED first so every subsequent step can be shown on screen
  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    oledReady = true;
    display.setTextWrap(false);
    display.clearDisplay();
    display.display();
    Serial.println("[OLED] Ready (128×64)");
  } else {
    Serial.println("[OLED] Not found — continuing without display");
  }

  String uid = chipUID();
  Serial.printf("  Chip UID : %s\n", uid.c_str());
  Serial.println("  ↑ Use this UID to register device in the Vita app\n");

  // Boot splash — show UID so user can note it down
  char uidLine[22];
  snprintf(uidLine, sizeof(uidLine), "%.17s", uid.c_str());
  oledShow("VITA STATION", "Booting...", uidLine, "Note UID for app");
  delay(2500);

  // WiFi
  connectWiFi();

  // Time sync
  syncNTP();

  // Sensors
  dht.begin();
  Serial.println("[DHT11] Initialized");

#if ENABLE_HX711
  initHX711();
  oledShow("VITA STATION", "Sensors ready:",
           "DHT11:  OK",
           scaleReady ? "HX711:  OK" : "HX711:  NOT FOUND");
#else
  oledShow("VITA STATION", "Sensors ready:",
           "DHT11:  OK",
           "HX711:  disabled");
#endif
  delay(1500);

  char intervalLine[22];
  snprintf(intervalLine, sizeof(intervalLine), "Post every %d s", POST_INTERVAL_MS / 1000);
  oledShow("VITA STATION", "All systems ready!", intervalLine);
  Serial.printf("\n  Posting every %d s → %s\n\n", POST_INTERVAL_MS / 1000, SERVER_INGEST_URL);
  delay(1000);
  ledBlink(5, 80);
}

void loop() {
  unsigned long now = millis();
  if (now - lastPostMs < POST_INTERVAL_MS) return;
  lastPostMs = now;

  Serial.println("──────────────────────────────────────────");
  Serial.println("[Vita] Reading station sensors...");
  oledShow("VITA STATION", "Reading sensors...");

  float humidity    = NAN;
  float ambientTemp = NAN;
  float weight      = NAN;

  readDHT11(humidity, ambientTemp);
  lastHumidity = humidity;
  lastAmbTemp  = ambientTemp;

#if ENABLE_HX711
  readHX711(weight);
  lastWeight = weight;
#endif

  postVitals(humidity, weight);
  Serial.println("──────────────────────────────────────────\n");
}
