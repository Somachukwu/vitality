// ============================================================
//  VITA WEARABLE — ESP32 Firmware
//  Worn on the wrist / chest. Reads biometric sensors and
//  POSTs heart rate, SpO2, body temperature, and steps to
//  the Vita backend every POST_INTERVAL_MS milliseconds.
//
//  Sensors (all on I2C bus — SDA=GPIO21, SCL=GPIO22):
//    • MAX30102  — Heart rate + SpO2
//    • MLX90614  — Non-contact IR body temperature
//    • MPU6050   — Accelerometer + Gyroscope (step counting)
//    • SSD1306   — 128×64 OLED status display (shares same I2C bus)
//
//  Required libraries (Arduino IDE → Tools → Manage Libraries):
//    • ArduinoJson            by Benoit Blanchon        v6.x
//    • SparkFun MAX3010x      by SparkFun Electronics
//    • Adafruit MLX90614      by Adafruit
//    • MPU6050                by Electronic Cats
//    • Adafruit SSD1306       by Adafruit
//    • Adafruit GFX Library   by Adafruit
//
//  Wiring:
//  ┌──────────────┬──────────────────────────────────────────────┐
//  │ ESP32 Pin    │ Connected to                                  │
//  ├──────────────┼──────────────────────────────────────────────┤
//  │ 3V3          │ MAX30102 VIN, MLX90614 VIN, MPU6050 VCC,     │
//  │              │ OLED VCC                                      │
//  │ GND          │ MAX30102 GND, MLX90614 GND, MPU6050 GND,     │
//  │              │ OLED GND                                      │
//  │ GPIO 21 (SDA)│ MAX30102 SDA, MLX90614 SDA, MPU6050 SDA,    │
//  │              │ OLED SDA                                      │
//  │ GPIO 22 (SCL)│ MAX30102 SCL, MLX90614 SCL, MPU6050 SCL,    │
//  │              │ OLED SCL                                      │
//  │ GPIO 2       │ Built-in LED (status indicator)               │
//  └──────────────┴──────────────────────────────────────────────┘
//  I2C addresses: MAX30102=0x57, MLX90614=0x5A, MPU6050=0x68, OLED=0x3C
//  No address conflicts — all four can share the same bus.
// ============================================================

#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// Sensor libraries
#include <MAX30105.h>
#include <spo2_algorithm.h>
#include <Adafruit_MLX90614.h>
#include <MPU6050.h>

#include "config.h"

// ── Sensor objects ────────────────────────────────────────────
MAX30105          particleSensor;
Adafruit_MLX90614 mlx;
MPU6050           mpu;

// ── OLED ─────────────────────────────────────────────────────
Adafruit_SSD1306 display(128, 64, &Wire, -1);
bool oledReady = false;

// MAX30102 sample buffers
uint32_t irBuffer[HR_BUFFER_LEN];
uint32_t redBuffer[HR_BUFFER_LEN];
int32_t  spo2Result;
int8_t   validSPO2;
int32_t  hrResult;
int8_t   validHR;

// Step counting state
volatile int32_t  stepCount         = 0;
float             lastMag           = 1.0f;
bool              stepArmed         = false;
unsigned long     lastStepMs        = 0;

// Gyroscope data (collected for future use — not yet in backend schema)
struct GyroSnapshot { float gx, gy, gz; };
GyroSnapshot lastGyro = {0, 0, 0};

// Timing
unsigned long lastPostMs    = 0;
unsigned long lastMpuMs     = 0;
unsigned long lastOledMs    = 0;   // 1-second OLED clock refresh
bool          ntpSynced     = false;
bool          setupDone     = false;
bool          max30102Ready = false;
bool          mlxReady      = false;
bool          mpuReady      = false;

// Last reading cache — used by oledRefreshData()
String  lastPostStatus  = "--";
String  lastPostTime    = "--:--:--";
float   lastHeartRate   = NAN;
float   lastSpo2        = NAN;
float   lastTemperature = NAN;
int32_t lastSteps       = 0;

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

// Draw inverted title bar at y=0..10.  Always shows live time once NTP is synced.
static void _oledHeader(const char* label) {
  display.fillRect(0, 0, 128, 11, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK);
  display.setCursor(2, 2);
  display.print(label);
  if (ntpSynced) {
    struct tm t;
    if (getLocalTime(&t)) {
      char tbuf[6];
      strftime(tbuf, sizeof(tbuf), "%H:%M", &t);
      display.setCursor(92, 2);
      display.print(tbuf);
    }
  }
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

// Live data dashboard — refreshed every second in loop() for a live clock
void oledRefreshData() {
  if (!oledReady) return;
  display.clearDisplay();
  _oledHeader("VITA WEARABLE");   // draws title + live time

  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // Row 1 — Heart Rate + SpO2
  display.setCursor(0, 14);
  {
    char hrStr[5], o2Str[6];
    if (!isnan(lastHeartRate)) snprintf(hrStr, sizeof(hrStr), "%d", (int)lastHeartRate);
    else strcpy(hrStr, "--");
    if (!isnan(lastSpo2)) snprintf(o2Str, sizeof(o2Str), "%d%%", (int)lastSpo2);
    else strcpy(o2Str, "--%");
    char buf[22];
    snprintf(buf, sizeof(buf), "HR:%s bpm  O2:%s", hrStr, o2Str);
    display.print(buf);
  }

  // Row 2 — Body Temperature
  display.setCursor(0, 25);
  if (!isnan(lastTemperature)) {
    char buf[18];
    snprintf(buf, sizeof(buf), "Tmp: %.1f C", lastTemperature);
    display.print(buf);
  } else {
    display.print("Tmp: --");
  }

  // Row 3 — Steps
  display.setCursor(0, 36);
  if (mpuReady) {
    char buf[18];
    snprintf(buf, sizeof(buf), "Steps: %d", (int)lastSteps);
    display.print(buf);
  } else {
    display.print("Steps: (no MPU)");
  }

  // Divider
  display.drawLine(0, 48, 127, 48, SSD1306_WHITE);

  // Row 4 — Last POST result + timestamp
  display.setCursor(0, 52);
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

  oledShow("VITA WEARABLE", "Connecting to WiFi:", ssidLine, "Please wait...");
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
      oledShow("VITA WEARABLE", "Connecting to WiFi:", ssidLine, tryLine);
    }
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n[WiFi] Failed — restarting in 5 s");
    oledShow("VITA WEARABLE", "WiFi FAILED!", "Restarting in 5s...");
    delay(5000);
    ESP.restart();
  }

  Serial.printf("\n[WiFi] Connected  IP: %s\n", WiFi.localIP().toString().c_str());
  char ipLine[22];
  snprintf(ipLine, sizeof(ipLine), "IP: %s", WiFi.localIP().toString().c_str());
  oledShow("VITA WEARABLE", "WiFi Connected!", ssidLine, ipLine);
  delay(2000);
  ledBlink(3);
}

void ensureWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Lost — reconnecting");
    oledShow("VITA WEARABLE", "WiFi lost!", "Reconnecting...");
    connectWiFi();
  }
}

void syncNTP() {
  oledShow("VITA WEARABLE", "Syncing time...", NTP_SERVER);
  configTime(GMT_OFFSET_S, DST_OFFSET_S, NTP_SERVER);
  Serial.print("[NTP]  Syncing");
  struct tm t; int tries = 0;
  while (!getLocalTime(&t) && tries < 20) { delay(500); Serial.print("."); tries++; }
  if (getLocalTime(&t)) {
    ntpSynced = true;
    Serial.printf("\n[NTP]  Synced: %s", asctime(&t));
    char timeLine[22];
    strftime(timeLine, sizeof(timeLine), "%d %b  %H:%M:%S", &t);
    oledShow("VITA WEARABLE", "Time Synced!", timeLine);
    delay(2000);
  } else {
    Serial.println("\n[NTP]  Failed — server will timestamp");
    oledShow("VITA WEARABLE", "NTP sync failed!", "Server will timestamp");
    delay(1500);
  }
}

// Pings /api/health before the main loop so the user knows immediately
// whether the server is reachable and the API key is accepted.
void checkServerReachable() {
  oledShow("VITA WEARABLE", "Checking server...", SERVER_HEALTH_URL);
  Serial.printf("[Server] Pinging %s ...", SERVER_HEALTH_URL);

  HTTPClient http;
  http.begin(SERVER_HEALTH_URL);
  http.setTimeout(6000);
  int code = http.GET();
  http.end();

  if (code == 200) {
    Serial.println(" OK");
    oledShow("VITA WEARABLE", "Server: ONLINE", "Backend is reachable");
  } else if (code > 0) {
    char msg[22];
    snprintf(msg, sizeof(msg), "HTTP %d from server", code);
    Serial.printf(" HTTP %d\n", code);
    oledShow("VITA WEARABLE", "Server: responded", msg);
  } else {
    Serial.printf(" FAILED: %s\n", HTTPClient::errorToString(code).c_str());
    oledShow("VITA WEARABLE", "Server: OFFLINE!",
             "Check IP in config.h",
             "uvicorn --host 0.0.0.0");
  }
  delay(2500);
}

// Verifies the device API key against the backend database.
// Returns true if the key is valid and active.
// Shows a clear actionable message on the OLED for each failure mode.
bool checkApiKey() {
  oledShow("VITA WEARABLE", "Checking API key...", SERVER_DEVICE_STATUS_URL);
  Serial.printf("[Auth] GET %s\n", SERVER_DEVICE_STATUS_URL);

  HTTPClient http;
  http.begin(SERVER_DEVICE_STATUS_URL);
  http.addHeader("X-API-Key", DEVICE_API_KEY);
  http.setTimeout(6000);
  int code = http.GET();
  String resp = http.getString();
  http.end();

  Serial.printf("[Auth] Response %d: %s\n", code, resp.c_str());

  if (code == 200) {
    oledShow("VITA WEARABLE", "API key: VALID", "Device registered", "Ready to send data");
    delay(2000);
    return true;
  } else if (code == 401) {
    oledShow("VITA WEARABLE", "API key: NOT FOUND!",
             "Register device:",
             "App > Profile > Devices",
             "Then copy key here");
    Serial.println("[Auth] DEVICE NOT REGISTERED.");
    Serial.println("[Auth] Steps: open Vita app > Profile > Add Device > paste Chip UID.");
    Serial.println("[Auth] Copy the returned api_key into vita_wearable/config.h and reflash.");
    delay(5000);
    return false;
  } else if (code > 0) {
    char msg[22];
    snprintf(msg, sizeof(msg), "HTTP %d from server", code);
    oledShow("VITA WEARABLE", "Auth check error", msg, "Check backend logs");
    Serial.printf("[Auth] Unexpected HTTP %d — check backend logs.\n", code);
    delay(3000);
    return false;
  } else {
    oledShow("VITA WEARABLE", "Cannot reach server!",
             "Check IP + firewall",
             "uvicorn --host 0.0.0.0");
    Serial.printf("[Auth] Connection failed: %s\n", HTTPClient::errorToString(code).c_str());
    delay(3000);
    return false;
  }
}

// ─────────────────────────────────────────────────────────────
//  MAX30102 — Heart Rate + SpO2
// ─────────────────────────────────────────────────────────────

bool initMAX30102() {
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("[MAX30102] Not found — check SDA/SCL wiring");
    return false;
  }
  // ledBrightness=60, sampleAverage=4, ledMode=2 (Red+IR),
  // sampleRate=100 Hz, pulseWidth=411 µs, adcRange=4096
  particleSensor.setup(60, 4, 2, 100, 411, 4096);
  particleSensor.setPulseAmplitudeRed(0x0A);
  particleSensor.setPulseAmplitudeGreen(0);
  Serial.println("[MAX30102] Ready");
  return true;
}

// Attempts to read HR + SpO2 from MAX30102.
// FAST PATH: if no finger is detected on the sensor, returns immediately
// with NAN values so the rest of the sensors are not held up.
// SLOW PATH: if a finger is present, collects HR_BUFFER_LEN samples (~1 s)
// and runs the SpO2 algorithm.
bool readMAX30102(float& heartRate, float& spo2) {
  heartRate = NAN; spo2 = NAN;

  long irCheck = particleSensor.getIR();
  if (irCheck < 50000) {
    Serial.println("[MAX30102] No finger detected — skipping HR/SpO2 this cycle");
    Serial.println("[MAX30102] Other sensor data will still be posted.");
    return false;
  }

  Serial.printf("[MAX30102] Finger present — collecting %d samples...\n", HR_BUFFER_LEN);
  for (int i = 0; i < HR_BUFFER_LEN; i++) {
    while (!particleSensor.available()) particleSensor.check();
    redBuffer[i] = particleSensor.getRed();
    irBuffer[i]  = particleSensor.getIR();
    particleSensor.nextSample();
  }

  maxim_heart_rate_and_oxygen_saturation(
    irBuffer, HR_BUFFER_LEN, redBuffer,
    &spo2Result, &validSPO2,
    &hrResult,   &validHR
  );

  bool gotHR = validHR   && hrResult   >= HR_MIN_VALID  && hrResult   <= HR_MAX_VALID;
  bool gotO2 = validSPO2 && spo2Result >= SPO2_MIN_VALID && spo2Result <= 100;

  if (gotHR) { heartRate = (float)hrResult;   Serial.printf("[MAX30102] HR:   %d bpm\n", hrResult); }
  else          Serial.println("[MAX30102] HR invalid — ensure firm, still finger contact");

  if (gotO2) { spo2 = (float)spo2Result; Serial.printf("[MAX30102] SpO2: %d%%\n", spo2Result); }
  else          Serial.println("[MAX30102] SpO2 invalid");

  return gotHR || gotO2;
}

// ─────────────────────────────────────────────────────────────
//  MLX90614 — Non-contact IR Body Temperature
// ─────────────────────────────────────────────────────────────

bool initMLX90614() {
  if (!mlx.begin(MLX90614_I2C_ADDR)) {
    Serial.println("[MLX90614] Not found — check SDA/SCL wiring");
    return false;
  }
  Serial.printf("[MLX90614] Ready  emissivity=%.2f\n", mlx.readEmissivity());
  return true;
}

// Reads object (body surface) temperature.
// MLX90614 needs to be held ~2–5 cm from the skin (wrist / forehead).
// Normal body surface: 32–37 °C depending on ambient and placement.
bool readMLX90614(float& tempC) {
  tempC = mlx.readObjectTempC();
  float ambient = mlx.readAmbientTempC();

  if (isnan(tempC) || tempC < 20.0f || tempC > 50.0f) {
    Serial.printf("[MLX90614] Reading out of range: %.1f°C — check placement\n", tempC);
    tempC = NAN;
    return false;
  }
  Serial.printf("[MLX90614] Object: %.1f°C  Ambient: %.1f°C\n", tempC, ambient);
  return true;
}

// ─────────────────────────────────────────────────────────────
//  MPU6050 — Accelerometer + Gyroscope
// ─────────────────────────────────────────────────────────────

bool initMPU6050() {
  mpu.initialize();
  mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);   // ±2g — best sensitivity for steps
  mpu.setFullScaleGyroRange(MPU6050_GYRO_FS_250);   // ±250°/s
  if (!mpu.testConnection()) {
    Serial.println("[MPU6050] Not found — check SDA/SCL wiring and AD0 pin");
    return false;
  }
  Serial.println("[MPU6050] Ready  (±2g accel, ±250°/s gyro)");
  return true;
}

// Called every MPU_POLL_MS from loop() — NOT during the sensor read block.
// Uses a two-threshold (hysteresis) peak detector for reliable step counting.
void updateStepCount() {
  if (!mpuReady) return;

  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

  // Accel: convert raw to g  (±2g range → 16384 LSB/g)
  float fx = ax / 16384.0f;
  float fy = ay / 16384.0f;
  float fz = az / 16384.0f;
  float mag = sqrtf(fx*fx + fy*fy + fz*fz);

  // Gyro: convert raw to °/s  (±250°/s range → 131 LSB/°/s)
  lastGyro = { gx / 131.0f, gy / 131.0f, gz / 131.0f };

  unsigned long now = millis();

  // Hysteresis peak detector
  if (!stepArmed && mag > STEP_HIGH_G) {
    stepArmed = true;
  } else if (stepArmed && mag < STEP_LOW_G) {
    stepArmed = false;
    if (now - lastStepMs > STEP_MIN_MS) {
      stepCount++;
      lastStepMs = now;
    }
  }
  lastMag = mag;
}

// ─────────────────────────────────────────────────────────────
//  HTTP POST to Vita backend
// ─────────────────────────────────────────────────────────────

void postVitals(float heartRate, float spo2, float temperature, int32_t steps) {
  ensureWiFi();

  HTTPClient http;
  http.begin(SERVER_INGEST_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key",    DEVICE_API_KEY);
  http.setTimeout(SERVER_TIMEOUT_MS);

  StaticJsonDocument<256> doc;
  if (!isnan(heartRate))   doc["heart_rate"]  = heartRate;
  if (!isnan(spo2))        doc["spo2"]         = spo2;
  if (!isnan(temperature)) doc["temperature"]  = temperature;
  if (steps >= 0)          doc["steps"]        = steps;

  String ts = isoTimestamp();
  if (ts.length())         doc["recorded_at"]  = ts;

  String body;
  serializeJson(doc, body);

  Serial.printf("[HTTP] POST → %s\n[HTTP] Body: %s\n", SERVER_INGEST_URL, body.c_str());

  // Show "Sending..." with exact data being transmitted
  {
    char l1[22], l2[22], l3[22];
    char hrStr[5], o2Str[5];
    if (!isnan(heartRate)) snprintf(hrStr, sizeof(hrStr), "%d", (int)heartRate);
    else strcpy(hrStr, "--");
    if (!isnan(spo2)) snprintf(o2Str, sizeof(o2Str), "%d", (int)spo2);
    else strcpy(o2Str, "--");
    snprintf(l1, sizeof(l1), "HR:%s bpm  O2:%s%%", hrStr, o2Str);
    if (!isnan(temperature))
      snprintf(l2, sizeof(l2), "Tmp: %.1f C", temperature);
    else
      strcpy(l2, "Tmp: --");
    snprintf(l3, sizeof(l3), "Steps: %d", (int)steps);
    oledShow("VITA WEARABLE", "Sending to server...", l1, l2, l3);
  }

  ledOn();
  int code = http.POST(body);
  ledOff();

  if (code == 201) {
    Serial.println("[HTTP] 201 Created — vitals saved ✓");
    lastPostStatus = "OK";
  } else if (code > 0) {
    String errBody = http.getString();
    Serial.printf("[HTTP] Error %d: %s\n", code, errBody.c_str());
    char codeStr[5];
    snprintf(codeStr, sizeof(codeStr), "%d", code);
    lastPostStatus = String(codeStr);
    // Show the OLED error for 3 s so the user can read it
    if (code == 401)
      oledShow("VITA WEARABLE", "POST: 401 Unauth",
               "Key invalid/inactive",
               "Run diagnose.py");
    else if (code == 422)
      oledShow("VITA WEARABLE", "POST: 422 Bad data",
               "JSON format error",
               "Check Serial monitor");
    else {
      char errLine[22];
      snprintf(errLine, sizeof(errLine), "Server HTTP %d", code);
      oledShow("VITA WEARABLE", "POST Failed", errLine,
               "Check backend logs");
    }
    delay(3000);
  } else {
    Serial.printf("[HTTP] Connection failed: %s\n", HTTPClient::errorToString(code).c_str());
    lastPostStatus = "FAIL";
    oledShow("VITA WEARABLE", "POST: No connection",
             "Server unreachable",
             "Run find_server_ip.py",
             "Then reflash");
    delay(3000);
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
  Serial.println("║   VITA WEARABLE — ESP32 Firmware         ║");
  Serial.println("╚══════════════════════════════════════════╝");

  Wire.begin();  // SDA=GPIO21, SCL=GPIO22 — shared by all I2C devices + OLED

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
  oledShow("VITA WEARABLE", "Booting...", uidLine, "Note UID for app");
  delay(2500);

  // WiFi
  connectWiFi();

  // Time sync
  syncNTP();

  // Sensors
  oledShow("VITA WEARABLE", "Initialising sensors", "Please wait...");
  delay(500);

  max30102Ready = initMAX30102();
  mlxReady      = initMLX90614();
  mpuReady      = initMPU6050();

  // Show sensor status on OLED
  oledShow("VITA WEARABLE",
           max30102Ready ? "MAX30102: OK" : "MAX30102: NOT FOUND",
           mlxReady      ? "MLX90614: OK" : "MLX90614: NOT FOUND",
           mpuReady      ? "MPU6050:  OK" : "MPU6050:  NOT FOUND");

  Serial.println();
  Serial.printf("  Sensor status:\n");
  Serial.printf("    MAX30102  (HR/SpO2)  : %s\n", max30102Ready ? "OK" : "NOT FOUND");
  Serial.printf("    MLX90614  (Temp)     : %s\n", mlxReady      ? "OK" : "NOT FOUND");
  Serial.printf("    MPU6050   (Steps)    : %s\n", mpuReady      ? "OK" : "NOT FOUND");
  delay(2000);

  // 1. Can we reach the server at all?
  checkServerReachable();

  // 2. Is this device registered in the backend database?
  checkApiKey();

  char intervalLine[22];
  snprintf(intervalLine, sizeof(intervalLine), "Post every %d s", POST_INTERVAL_MS / 1000);
  oledShow("VITA WEARABLE", "All systems ready!", intervalLine);
  Serial.printf("\n  Posting every %d s → %s\n\n", POST_INTERVAL_MS / 1000, SERVER_INGEST_URL);
  delay(1000);
  ledBlink(5, 80);

  setupDone = true;   // enables the 1-second OLED clock tick in loop()
}

void loop() {
  unsigned long now = millis();

  // Poll MPU6050 frequently for accurate step counting (never touches OLED)
  if (mpuReady && (now - lastMpuMs >= MPU_POLL_MS)) {
    lastMpuMs = now;
    updateStepCount();
  }

  // Tick the OLED clock every second — keeps the time live at all times
  if (setupDone && oledReady && ntpSynced && (now - lastOledMs >= 1000)) {
    lastOledMs = now;
    oledRefreshData();
  }

  // Full sensor read + POST on interval
  if (now - lastPostMs < POST_INTERVAL_MS) return;
  lastPostMs = now;

  Serial.println("──────────────────────────────────────────");
  Serial.println("[Vita] Reading wearable sensors...");

  float heartRate   = NAN;
  float spo2        = NAN;
  float temperature = NAN;

  // Read fast sensors first — these return immediately
  if (mlxReady) readMLX90614(temperature);

  // Read MAX30102 — returns instantly if no finger, ~1 s if finger is present
  if (max30102Ready) readMAX30102(heartRate, spo2);

  // Snapshot and reset step counter
  int32_t stepsThisInterval = stepCount;
  stepCount = 0;
  if (mpuReady) Serial.printf("[MPU6050] Steps this interval: %d\n", stepsThisInterval);

  // Log gyroscope (available for future features like fall detection)
  if (mpuReady) {
    Serial.printf("[MPU6050] Gyro  gX=%.1f  gY=%.1f  gZ=%.1f  °/s\n",
                  lastGyro.gx, lastGyro.gy, lastGyro.gz);
  }

  // Cache readings for OLED data view
  lastHeartRate   = heartRate;
  lastSpo2        = spo2;
  lastTemperature = temperature;
  lastSteps       = stepsThisInterval;

  postVitals(heartRate, spo2, temperature, mpuReady ? stepsThisInterval : -1);
  Serial.println("──────────────────────────────────────────\n");
}
