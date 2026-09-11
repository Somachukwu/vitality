// ============================================================
//  VITALITY — Device UID Extractor
//  Upload this sketch to your ESP32 to instantly read its
//  unique factory hardware Chip UID (MAC address).
//
//  Serial Monitor: 115200 baud
// ============================================================

#define LED_PIN 2

String getChipUID() {
  uint64_t mac = ESP.getEfuseMac();
  char buf[18];
  snprintf(buf, sizeof(buf), "%02X:%02X:%02X:%02X:%02X:%02X",
    (uint8_t)mac, (uint8_t)(mac >> 8),  (uint8_t)(mac >> 16),
    (uint8_t)(mac >> 24), (uint8_t)(mac >> 32), (uint8_t)(mac >> 40));
  return String(buf);
}

void printUIDBanner(const String& uid) {
  Serial.println();
  Serial.println("====================================================");
  Serial.println("           VITALITY — DEVICE UID FINDER             ");
  Serial.println("====================================================");
  Serial.println();
  Serial.print("  >>> YOUR DEVICE UID:  ");
  Serial.println(uid);
  Serial.println();
  Serial.println("  Next Steps:");
  Serial.println("  1. Copy the UID above: " + uid);
  Serial.println("  2. Open the Vitality App in your browser:");
  Serial.println("     Local: http://localhost:8080/devices.html");
  Serial.println("     Cloud: https://vitality-659j.onrender.com/devices.html");
  Serial.println("  3. Click 'Pair New Device'");
  Serial.println("  4. Paste this UID, give it a name (e.g. Smart Scale)");
  Serial.println("  5. Choose device type: 'station'");
  Serial.println("  6. Copy the generated API Key into vita_station/config.h");
  Serial.println("====================================================");
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  delay(1500);

  String uid = getChipUID();
  printUIDBanner(uid);
}

void loop() {
  // Blink LED and reprint every 4 seconds so you never miss it
  digitalWrite(LED_PIN, HIGH);
  delay(100);
  digitalWrite(LED_PIN, LOW);
  delay(3900);

  String uid = getChipUID();
  Serial.print("[Live] Device UID: ");
  Serial.println(uid);
}
