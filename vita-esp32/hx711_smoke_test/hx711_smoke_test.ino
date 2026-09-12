// =============================================================================
//  VITA STATION — HX711 Hardware Signal Smoke Test
//  
//  Use this sketch to test if your HX711 ADC and load cells are physically
//  connected, powered, and sending real 24-bit signals to the ESP32.
//
//  Hardware Pinout (matches vita_station/config.h):
//    • ESP32 GPIO 19 ----> HX711 DOUT
//    • ESP32 GPIO 18 ----> HX711 SCK
//    • ESP32 GPIO 2  ----> Onboard Status LED
//    • ESP32 5V (VIN) ---> HX711 VCC (Must be 5V, 3.3V often causes failure)
//    • ESP32 GND     ----> HX711 GND
//
//  Load Cell Wiring to HX711:
//    • Red   ----> E+ (Excitation +)
//    • Black ----> E- (Excitation -)
//    • White ----> A- (Signal -)
//    • Green ----> A+ (Signal +)
//
//  Instructions:
//    1. Open Arduino IDE and select your ESP32 board.
//    2. Ensure "HX711 Arduino Library" by bogde is installed.
//    3. Upload this sketch.
//    4. Open Serial Monitor at 115200 baud.
//    5. Watch the live raw values and press on the scale with your hand.
// =============================================================================

#include <Arduino.h>
#include <HX711.h>

#define DOUT_PIN 19
#define SCK_PIN  18
#define LED_PIN  2

HX711 scale;

// Baseline tracking for pressure detection
long baselineRaw = 0;
bool baselineSet = false;
unsigned long readCount = 0;
unsigned long lastHzCheck = 0;
int readsThisSecond = 0;
float currentHz = 0.0;

void printTroubleshootingHelp(const char* reason) {
  Serial.println("\n-------------------------------------------------------------");
  Serial.printf(" [DIAGNOSTIC ALERT] %s\n", reason);
  Serial.println("-------------------------------------------------------------");
  Serial.println(" Common Causes & Fixes:");
  Serial.println("  1. Power: Make sure HX711 VCC is wired to 5V (VIN), NOT 3.3V.");
  Serial.println("  2. Pins: Verify DOUT -> GPIO 19 and SCK -> GPIO 18.");
  Serial.println("  3. DOUT Stuck HIGH: No power to HX711, or DOUT wire disconnected.");
  Serial.println("  4. DOUT Stuck LOW: Short to GND on DOUT or damaged module.");
  Serial.println("  5. Saturated at +/-8388607 or 0: Load cell wires disconnected");
  Serial.println("     (Check Red=E+, Black=E-, White=A-, Green=A+).");
  Serial.println("-------------------------------------------------------------\n");
}

void setup() {
  Serial.begin(115200);
  delay(1200);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println();
  Serial.println("=============================================================");
  Serial.println("   VITA STATION — HX711 SIGNAL SMOKE TEST");
  Serial.println("=============================================================");
  Serial.printf("  Pins Configured: DOUT = GPIO %d | SCK = GPIO %d | LED = GPIO %d\n", DOUT_PIN, SCK_PIN, LED_PIN);
  Serial.println("=============================================================\n");

  // Step 1: Direct GPIO state test before library takes over
  Serial.println("[STEP 1] Direct GPIO Probe:");
  pinMode(DOUT_PIN, INPUT_PULLUP);
  int initialDout = digitalRead(DOUT_PIN);
  Serial.printf("         Raw DOUT logic level: %s\n", initialDout == HIGH ? "HIGH (Idle or Unconnected)" : "LOW (Ready / Pull-down)");

  // Step 2: Initialize Bogde HX711 library
  Serial.println("[STEP 2] Initializing HX711 Driver...");
  scale.begin(DOUT_PIN, SCK_PIN);

  // Step 3: Wait for first signal transition (timeout 3500ms)
  Serial.print("[STEP 3] Listening for HX711 DOUT conversion pulse");
  unsigned long startWait = millis();
  bool responsive = false;

  while (millis() - startWait < 3500) {
    if (scale.is_ready()) {
      responsive = true;
      break;
    }
    delay(100);
    Serial.print(".");
  }

  if (responsive) {
    Serial.printf(" READY! (Responded in %lu ms)\n", millis() - startWait);
    Serial.println("\n >>> SUCCESS: The HX711 is actively pulsing and sending signals! <<<\n");
    // Blink LED 3 times to signal success
    for (int i = 0; i < 3; i++) {
      digitalWrite(LED_PIN, HIGH); delay(100);
      digitalWrite(LED_PIN, LOW);  delay(100);
    }
  } else {
    Serial.println(" TIMEOUT!");
    printTroubleshootingHelp("HX711 did not respond (DOUT pin never went LOW within 3.5 seconds).");
    Serial.println("[INFO] Continuing loop to keep monitoring pin in case wires are reconnected...\n");
  }

  Serial.println("=============================================================");
  Serial.println(" LIVE 24-BIT SIGNAL MONITOR (Press your hand on the scale)");
  Serial.println(" Format: Raw Value | Delta from Baseline | Signal Bar | Est. Hz");
  Serial.println("=============================================================");
}

// ── Print interval — 1000ms (1 second) so it is calm and easy to read ──────
#define PRINT_INTERVAL_MS 1000UL

// Accumulator for averaging across the 1-second window
long rawSum = 0;
long minRawInWindow = 0;
long maxRawInWindow = 0;
int windowSamples = 0;
unsigned long lastPrintMs = 0;

void loop() {
  // Check for user input (type 't' and press enter to re-tare)
  if (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 't' || c == 'T') {
      if (windowSamples > 0) {
        baselineRaw = rawSum / windowSamples;
      }
      Serial.println("\n-------------------------------------------------------------");
      Serial.printf(" [TARE RESET] New baseline set to: %ld\n", baselineRaw);
      Serial.println("-------------------------------------------------------------\n");
    }
  }

  // Continuously read samples from HX711 as fast as they are ready
  if (scale.is_ready()) {
    long raw = scale.read();
    readCount++;
    readsThisSecond++;

    if (!baselineSet) {
      baselineRaw = raw;
      baselineSet = true;
      Serial.println("\n-------------------------------------------------------------");
      Serial.printf(" [BASELINE CAPTURED] Initial tare baseline: %ld\n", baselineRaw);
      Serial.println(" (Tip: Type 't' and press Enter at any time to re-zero the scale)");
      Serial.println("-------------------------------------------------------------\n");
      lastPrintMs = millis();
    }

    if (windowSamples == 0) {
      minRawInWindow = raw;
      maxRawInWindow = raw;
    } else {
      if (raw < minRawInWindow) minRawInWindow = raw;
      if (raw > maxRawInWindow) maxRawInWindow = raw;
    }
    rawSum += raw;
    windowSamples++;

    // Brief LED flash for hardware signal confirmation
    digitalWrite(LED_PIN, HIGH);
    delayMicroseconds(500);
    digitalWrite(LED_PIN, LOW);
  }

  // Print a clean, calm summary line once every second
  unsigned long now = millis();
  if (now - lastPrintMs >= PRINT_INTERVAL_MS) {
    if (windowSamples > 0) {
      long avgRaw = rawSum / windowSamples;
      long delta = avgRaw - baselineRaw;
      long absDelta = abs(delta);
      float sampleRate = (float)windowSamples * 1000.0f / (float)(now - lastPrintMs);

      // Activity meter bar
      char bar[15] = "          ";
      int bars = min(10, (int)(absDelta / 20000L));
      for (int b = 0; b < bars; b++) bar[b] = '=';

      const char* statusStr = "IDLE (Scale Empty)";
      if (absDelta > 30000) {
        statusStr = delta > 0 ? ">>> PRESSURE DETECTED! <<<" : ">>> NEGATIVE LOAD / LIFT <<<";
      } else if (absDelta > 8000) {
        statusStr = "LIGHT TOUCH";
      }

      Serial.printf("[Avg Raw: %10ld] | Delta: %+8ld | [%-10s] | %4.1f sps | %s\n",
                    avgRaw, delta, bar, sampleRate, statusStr);

      // Reset window
      rawSum = 0;
      windowSamples = 0;
    } else {
      Serial.println("[WAITING] No signal from HX711 in the last second... (Check wiring/VCC)");
    }
    lastPrintMs = now;
  }
}

