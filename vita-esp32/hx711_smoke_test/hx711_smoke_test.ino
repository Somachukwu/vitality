// =============================================================================
//  VITA STATION — Standalone Weight Measurement Test (No WiFi / No Backend)
//
//  Measures real-world weights in kilograms (kg) using your HX711 and load cell.
//  No Wi-Fi, no backend, no networking — pure scale telemetry.
//
//  Hardware Pinout:
//    • ESP32 GPIO 19 ----> HX711 DOUT
//    • ESP32 GPIO 18 ----> HX711 SCK
//    • ESP32 GPIO 2  ----> Onboard Status LED
//    • ESP32 5V (VIN) ---> HX711 VCC (Must be 5V)
//    • ESP32 GND     ----> HX711 GND
//
//  Serial Commands (type in Serial Monitor and press Enter):
//    • 't' -> Tare / Zero the scale (make sure scale is empty)
//    • Any number (e.g. "5.0") -> Calibrate with known weight in kg
// =============================================================================

#include <Arduino.h>
#include <HX711.h>

// Pins (matches vita_station/config.h)
#define DOUT_PIN 19
#define SCK_PIN  18
#define LED_PIN  2

// Calibration parameters from vita_station/config.h
#define DEFAULT_SCALE_FACTOR  20982.1289f
#define DEFAULT_SCALE_OFFSET  222644L

// Sampling
#define SAMPLES_PER_READ      5       // Number of readings averaged per cycle
#define REFRESH_INTERVAL_MS   500UL   // Update display every 500ms
#define EMPTY_THRESHOLD_KG    0.5f    // Below this is considered empty scale

HX711 scale;

float scaleFactor = DEFAULT_SCALE_FACTOR;
long  scaleOffset = DEFAULT_SCALE_OFFSET;

// Stability detection (like a commercial bathroom scale)
float lastWeightKg = 0.0f;
int   stableCount  = 0;
bool  isLocked     = false;
float lockedWeight = 0.0f;
unsigned long lastPrintMs = 0;

void setup() {
  Serial.begin(115200);
  delay(1200);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println();
  Serial.println("=============================================================");
  Serial.println("     VITA SCALE — REAL WEIGHT MEASUREMENT (STANDALONE)       ");
  Serial.println("=============================================================");
  Serial.printf(" Pins        : DOUT=GPIO%d, SCK=GPIO%d, LED=GPIO%d\n", DOUT_PIN, SCK_PIN, LED_PIN);
  Serial.printf(" Scale Factor: %.4f\n", scaleFactor);
  Serial.printf(" Scale Offset: %ld\n", scaleOffset);
  Serial.println("-------------------------------------------------------------");
  Serial.println(" Commands:");
  Serial.println("   Type 't' and press Enter to TARE (Zero) the scale.");
  Serial.println("   Type a known weight in kg (e.g. 5.0) to calibrate.");
  Serial.println("=============================================================\n");

  Serial.print("[INIT] Connecting to HX711...");
  scale.begin(DOUT_PIN, SCK_PIN);

  // Wait up to 3 seconds for HX711 ready
  unsigned long start = millis();
  while (!scale.is_ready() && millis() - start < 3000) {
    delay(100);
    Serial.print(".");
  }

  if (!scale.is_ready()) {
    Serial.println(" FAILED!");
    Serial.println("\n[ERROR] HX711 is not responding. Check DOUT=19, SCK=18, VCC=5V.");
    while (true) {
      digitalWrite(LED_PIN, HIGH); delay(200);
      digitalWrite(LED_PIN, LOW);  delay(200);
    }
  }

  Serial.println(" READY!");

  // Apply calibration factor and offset
  scale.set_scale(scaleFactor);
  scale.set_offset(scaleOffset);

  // Prompt tare
  Serial.println("[TARE] Performing initial tare with scale empty...");
  scale.tare(10);
  scaleOffset = scale.get_offset();
  Serial.printf("[TARE] Zero baseline calibrated (Offset: %ld)\n\n", scaleOffset);

  // Success blink
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH); delay(80);
    digitalWrite(LED_PIN, LOW);  delay(80);
  }

  Serial.println("-------------------------------------------------------------");
  Serial.println(" Step on the scale or place an object to measure weight:");
  Serial.println("-------------------------------------------------------------\n");
}

void loop() {
  // ── Handle Serial commands ('t' for tare, or number for calibration) ─────
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();

    if (input.equalsIgnoreCase("t")) {
      Serial.println("\n>>> Taring scale... Please ensure nothing is on the scale! <<<");
      scale.tare(15);
      scaleOffset = scale.get_offset();
      isLocked = false;
      stableCount = 0;
      Serial.printf(">>> ZERO TARE COMPLETE (New Offset: %ld) <<<\n\n", scaleOffset);
    } else {
      float knownKg = input.toFloat();
      if (knownKg > 0.1f) {
        Serial.printf("\n>>> Calibrating with known weight: %.2f kg... <<<\n", knownKg);
        long rawDiff = scale.read_average(15) - scaleOffset;
        scaleFactor = (float)rawDiff / knownKg;
        scale.set_scale(scaleFactor);
        isLocked = false;
        stableCount = 0;
        Serial.printf(">>> NEW SCALE FACTOR: %.4f <<<\n", scaleFactor);
        Serial.printf(">>> Update config.h: #define SCALE_FACTOR %.4ff <<<\n\n", scaleFactor);
      }
    }
  }

  // ── Read weight periodically ─────────────────────────────────────────────
  unsigned long now = millis();
  if (now - lastPrintMs >= REFRESH_INTERVAL_MS) {
    lastPrintMs = now;

    if (scale.is_ready()) {
      float weightKg = scale.get_units(SAMPLES_PER_READ);
      float weightLbs = weightKg * 2.20462f;

      // Filter micro-noise near zero
      if (abs(weightKg) < 0.10f) {
        weightKg = 0.0f;
        weightLbs = 0.0f;
      }

      // Check stability (variance < 0.25 kg between 500ms intervals)
      if (abs(weightKg - lastWeightKg) < 0.25f && weightKg >= EMPTY_THRESHOLD_KG) {
        stableCount++;
      } else {
        stableCount = 0;
        if (abs(weightKg - lastWeightKg) > 0.8f) {
          isLocked = false;
        }
      }
      lastWeightKg = weightKg;

      // Lock weight if steady for 3 consecutive checks (1.5 seconds)
      if (stableCount >= 3 && !isLocked) {
        isLocked = true;
        lockedWeight = weightKg;
        // Lock notification blink
        digitalWrite(LED_PIN, HIGH); delay(50); digitalWrite(LED_PIN, LOW); delay(50);
        digitalWrite(LED_PIN, HIGH);
      }

      // ── Print display ───────────────────────────────────────────────────
      if (weightKg < EMPTY_THRESHOLD_KG) {
        // Scale is empty
        digitalWrite(LED_PIN, LOW);
        isLocked = false;
        Serial.printf("[SCALE EMPTY]    0.00 kg  (  0.0 lbs)\n");
      } else if (isLocked) {
        // Weight is locked / stable
        digitalWrite(LED_PIN, HIGH);
        Serial.printf("[STABLE WEIGHT] *** %6.2f kg ***  (%5.1f lbs)  [LOCKED]\n", lockedWeight, lockedWeight * 2.20462f);
      } else {
        // Measuring / settling
        digitalWrite(LED_PIN, HIGH);
        Serial.printf("[MEASURING...]      %6.2f kg   (%5.1f lbs)\n", weightKg, weightLbs);
      }
    } else {
      Serial.println("[WAITING] HX711 busy or not ready...");
    }
  }
}
