// ============================================================
//  VITA SCALE CALIBRATOR — HX711 Calibration Sketch
//  Flash this ONCE to find SCALE_OFFSET and SCALE_FACTOR.
//  Then copy both values into vita_station/config.h and
//  re-flash vita_station.ino.
//
//  Required library:  HX711 Arduino Library  by bogde
//    Arduino IDE > Tools > Manage Libraries > search "HX711 bogde"
//
//  Wiring (must match vita_station/config.h):
//    ESP32 GPIO 3  ----> HX711 DOUT
//    ESP32 GPIO 2  ----> HX711 SCK
//    HX711 VCC     ----> ESP32 5V  (NEVER 3.3V — HX711 requires 5V)
//    HX711 GND     ----> ESP32 GND
//    Load cell E+/E-  -> HX711 E+/E-   (excitation, red/black wires)
//    Load cell A+/A-  -> HX711 A+/A-   (signal, white/green wires)
//
//  IMPORTANT — Serial Monitor setup:
//    Baud: 115200
//    Line ending: "Newline"  (dropdown at bottom of Serial Monitor)
//    To send a value: type it in the input box at the top, press Enter
//
//  Procedure:
//    1. Flash this sketch with NOTHING on the scale
//    2. Open Serial Monitor (115200, Newline)
//    3. Wait for STEP 1 to finish — note the printed SCALE_OFFSET value
//    4. Place a known reference weight on the scale
//    5. In the Serial Monitor INPUT BOX (top), type the kg value and press Enter
//       e.g.  type  2.0  for a 2 kg dumbbell
//    6. Note the printed SCALE_FACTOR value
//    7. Copy both into vita_station/config.h, then flash vita_station.ino
// ============================================================

#include <HX711.h>

// ── Pin config — must match HX711_DOUT_PIN / HX711_SCK_PIN in config.h ──
#define DOUT_PIN  3
#define SCK_PIN   2

// Internal sampling: read as fast as HX711 allows (~10 Hz)
// Display/print: every DISPLAY_INTERVAL_MS (10 seconds)
#define DISPLAY_INTERVAL_MS  10000UL

// Samples to average for the final calibration reading (more = more accurate)
#define CALIBRATION_SAMPLES  50

HX711 scale;

long   tareRaw      = 0;
bool   tareDone     = false;
bool   waitLoad     = false;
bool   calibrated   = false;
float  scaleFactor  = 1.0f;

// Rolling accumulator — collect readings continuously, display every 10 s
long           accumulator   = 0;
unsigned long  accumCount    = 0;
unsigned long  lastDisplayMs = 0;

String inputBuf = "";

// ─────────────────────────────────────────────────────────────
void printDivider() {
  Serial.println("----------------------------------------------");
}

void printBanner(const char* title) {
  printDivider();
  Serial.println(title);
  printDivider();
}

// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1500);   // let Serial Monitor open

  Serial.println();
  printBanner("=== VITA SCALE CALIBRATOR  (HX711) ===");
  Serial.println();
  Serial.println("Serial Monitor settings required:");
  Serial.println("  Baud : 115200");
  Serial.println("  Line ending : Newline  <-- IMPORTANT");
  Serial.println("  To enter a value: type in the TOP input box and press Enter");
  Serial.println();

  scale.begin(DOUT_PIN, SCK_PIN);

  Serial.print("Waiting for HX711");
  int tries = 0;
  while (!scale.is_ready() && tries < 40) {
    Serial.print(".");
    delay(500);
    tries++;
  }
  Serial.println();

  if (!scale.is_ready()) {
    Serial.println();
    Serial.println("!!! ERROR: HX711 NOT FOUND !!!");
    Serial.println("Check wiring:");
    Serial.println("  DOUT -> GPIO 3");
    Serial.println("  SCK  -> GPIO 2");
    Serial.println("  VCC  -> 5V  (NOT 3.3V)");
    Serial.println("  GND  -> GND");
    Serial.println("Press RST button on ESP32 to retry.");
    while (true) delay(1000);
  }

  Serial.println("HX711 detected OK");
  Serial.println();

  // ── STEP 1: Tare ─────────────────────────────────────────────
  printBanner("=== STEP 1: TARE (empty scale) ===");
  Serial.println("Make sure NOTHING is on the scale.");
  Serial.println("Collecting tare samples...");

  scale.set_scale();   // no calibration factor yet
  scale.tare();        // HX711 library internal tare (reference only)

  // Take a large average for the official tare value
  tareRaw = scale.read_average(CALIBRATION_SAMPLES);

  Serial.println();
  printBanner("--- TARE RESULT ---");
  Serial.print("SCALE_OFFSET = ");
  Serial.println(tareRaw);
  Serial.println();
  Serial.println("  #define SCALE_OFFSET  " + String(tareRaw) + "L");
  Serial.println();
  printDivider();

  // ── STEP 2: Prompt for known weight ──────────────────────────
  Serial.println();
  printBanner("=== STEP 2: PLACE YOUR KNOWN WEIGHT ===");
  Serial.println("1. Put a KNOWN weight on the scale now.");
  Serial.println("2. Wait for it to settle (5-10 seconds).");
  Serial.println("3. In the Serial Monitor input box (TOP of window),");
  Serial.println("   TYPE the weight in kilograms and press ENTER.");
  Serial.println("   Example:  2.0   for a 2 kg weight");
  Serial.println("             0.5   for a 500 g weight");
  Serial.println();
  Serial.println("Live raw readings will update every 10 seconds.");
  Serial.println("When the raw value is stable, enter the weight.");
  Serial.println();

  // Reset accumulator for step 2 live readings
  accumulator   = 0;
  accumCount    = 0;
  lastDisplayMs = millis();

  tareDone = true;
  waitLoad = true;
}

// ─────────────────────────────────────────────────────────────
void loop() {
  if (!tareDone) return;

  unsigned long now = millis();

  // ── Phase 1: Show live raw values every 10 s, wait for user input ──
  if (waitLoad) {

    // Accumulate every reading the HX711 produces (~10 Hz)
    if (scale.is_ready()) {
      accumulator += scale.read();
      accumCount++;
    }

    // Print summary every 10 seconds
    if (now - lastDisplayMs >= DISPLAY_INTERVAL_MS) {
      lastDisplayMs = now;

      long avg = (accumCount > 0) ? (accumulator / (long)accumCount) : 0;
      long diff = avg - tareRaw;

      Serial.println();
      Serial.println("[10s update]");
      Serial.print("  Avg raw  : "); Serial.println(avg);
      Serial.print("  Diff     : "); Serial.println(diff);
      Serial.println("  (When stable, enter weight in the input box above and press Enter)");
      Serial.println();

      // Reset accumulator for next window
      accumulator = 0;
      accumCount  = 0;
    }

    // Check Serial for user input (non-blocking)
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\n' || c == '\r') {
        inputBuf.trim();
        if (inputBuf.length() == 0) continue;

        float knownKg = inputBuf.toFloat();
        inputBuf = "";

        if (knownKg <= 0.0f) {
          Serial.println(">>> Invalid value. Enter a positive number in kg. <<<");
          continue;
        }

        // Take a precise average reading now
        Serial.println();
        Serial.println("Received: " + String(knownKg, 3) + " kg");
        Serial.println("Taking " + String(CALIBRATION_SAMPLES) + " precise samples...");

        long loadRaw = scale.read_average(CALIBRATION_SAMPLES);
        long diff    = loadRaw - tareRaw;
        scaleFactor  = (float)diff / knownKg;

        // ── Print results ─────────────────────────────────────
        Serial.println();
        printBanner("=== CALIBRATION RESULT ===");
        Serial.print("Known weight  : "); Serial.print(knownKg, 3); Serial.println(" kg");
        Serial.print("Tare raw      : "); Serial.println(tareRaw);
        Serial.print("Load raw      : "); Serial.println(loadRaw);
        Serial.print("Difference    : "); Serial.println(diff);
        Serial.println();
        printBanner("--- COPY THESE INTO vita_station/config.h ---");
        Serial.println();
        Serial.print("#define SCALE_FACTOR   "); Serial.print(scaleFactor, 4); Serial.println("f");
        Serial.print("#define SCALE_OFFSET   "); Serial.print(tareRaw); Serial.println("L");
        Serial.println("#define ENABLE_HX711   1");
        Serial.println();
        Serial.println("Then re-flash vita_station.ino");
        printDivider();
        Serial.println();
        printBanner("=== LIVE VERIFICATION ===");
        Serial.println("Step on / off the scale to verify accuracy.");
        Serial.println("Readings every 10 seconds.");
        Serial.println();

        scale.set_scale(scaleFactor);
        scale.set_offset(tareRaw);

        waitLoad      = false;
        calibrated    = true;
        accumulator   = 0;
        accumCount    = 0;
        lastDisplayMs = millis();
      } else {
        inputBuf += c;
      }
    }
  }

  // ── Phase 2: Live kg verification after calibration ───────────
  if (calibrated && !waitLoad) {

    // Accumulate readings
    if (scale.is_ready()) {
      // scale.get_units() with factor already set
      // We still accumulate raw and convert in bulk for accuracy
      accumulator += scale.read();
      accumCount++;
    }

    if (now - lastDisplayMs >= DISPLAY_INTERVAL_MS) {
      lastDisplayMs = now;

      float avgKg = 0.0f;
      if (accumCount > 0) {
        long avgRaw = accumulator / (long)accumCount;
        avgKg = (float)(avgRaw - tareRaw) / scaleFactor;
      }

      Serial.print("Live weight : ");
      Serial.print(avgKg, 3);
      Serial.println(" kg");

      accumulator = 0;
      accumCount  = 0;
    }
  }
}
